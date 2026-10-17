from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field as PField
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import admin_only
from app.core.errors import Conflict, NotFound, Unprocessable
from app.core.events import audit
from app.core.pagination import PageParams, paginate
from app.core.storage import get_storage
from app.ml.crop_vision import get_model
from app.modules.audit.models import AuditEvent
from app.modules.farms.models import CropReference
from app.modules.farms.router import crop_out
from app.modules.identity.models import Role, User
from app.modules.identity.router import user_out
from app.modules.monitoring.models import CropObservation, ModelPrediction, ModelRegistryEntry, PredictionStatus
from app.modules.monitoring.service import ensure_registry

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
def list_users(
    role: Role | None = None,
    q: str | None = Query(None, max_length=80),
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    stmt = select(User).order_by(User.role, User.full_name)
    if role:
        stmt = stmt.where(User.role == role)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where((User.full_name.ilike(like)) | (User.email.ilike(like)))

    def m(u: User):
        return {**user_out(u).model_dump(), "is_active": u.is_active, "last_login_at": u.last_login_at, "is_demo": u.is_demo}

    return paginate(db, stmt, params, m)


class UserUpdate(BaseModel):
    role: Role | None = None
    is_active: bool | None = None


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    u = db.get(User, user_id)
    if not u:
        raise NotFound("User not found.")
    if u.id == admin.id and (body.role not in (None, Role.ADMIN) or body.is_active is False):
        raise Conflict("You cannot remove your own administrator access.")
    before = {"role": u.role, "is_active": u.is_active}
    if body.role is not None and body.role != u.role:
        u.role = body.role.value
        u.token_version += 1  # forces re-login with the new role
    if body.is_active is not None and body.is_active != u.is_active:
        u.is_active = body.is_active
        u.token_version += 1
    audit(db, actor_id=admin.id, action="user.access_changed", entity_type="user", entity_id=u.id, before=before,
          after={"role": u.role, "is_active": u.is_active}, severity="security")
    db.commit()
    return {**user_out(u).model_dump(), "is_active": u.is_active, "last_login_at": u.last_login_at, "is_demo": u.is_demo}


class CropIn(BaseModel):
    code: str = PField(min_length=2, max_length=40, pattern=r"^[a-z0-9_]+$")
    name: str = PField(min_length=2, max_length=80)
    scientific_name: str | None = PField(default=None, max_length=120)
    category: str = PField(min_length=2, max_length=40)
    growth_stages: list[str] = PField(min_length=1, max_length=20)
    pollinator_dependent: bool = False
    vision_label_prefix: str | None = PField(default=None, max_length=60)


@router.post("/crops", status_code=201)
def create_crop(body: CropIn, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    if db.scalar(select(CropReference).where(CropReference.code == body.code)):
        raise Conflict("A crop with this code already exists.")
    model = get_model()
    if body.vision_label_prefix and model.available and body.vision_label_prefix not in model.supported_crops():
        raise Unprocessable("That prefix is not one of the model's crop classes.")
    c = CropReference(**body.model_dump())
    db.add(c)
    db.flush()
    audit(db, actor_id=admin.id, action="crop.created", entity_type="crop", entity_id=c.id, after=body.model_dump())
    db.commit()
    return crop_out(c)


@router.get("/models")
def models(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    m = get_model()
    entry = ensure_registry(db, m)
    db.commit()
    registry = db.scalars(select(ModelRegistryEntry).order_by(ModelRegistryEntry.created_at.desc())).all()
    counts = dict(
        db.execute(select(ModelPrediction.status, func.count(ModelPrediction.id)).group_by(ModelPrediction.status)).all()
    )
    return {
        "runtime": m.status(),
        "card": m.card,
        "registry": [
            {
                "id": r.id, "key": r.key, "version": r.version, "name": r.name, "task": r.task, "framework": r.framework,
                "artifact_sha256": r.artifact_sha256, "license": r.license, "status": r.status, "class_count": len(r.classes or []),
                "registered_at": r.created_at,
            }
            for r in registry
        ],
        "prediction_counts": counts,
        "active_registry_id": entry.id if entry else None,
    }


@router.get("/audit")
def audit_log(
    entity_type: str | None = None,
    severity: str | None = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if severity:
        stmt = stmt.where(AuditEvent.severity == severity)

    def m(e: AuditEvent):
        return {
            "id": e.id, "action": e.action, "entity_type": e.entity_type, "entity_id": e.entity_id, "summary": e.summary,
            "before": e.before, "after": e.after, "severity": e.severity, "actor": e.actor.full_name if e.actor else "System",
            "created_at": e.created_at,
        }

    return paginate(db, stmt, params, m)


@router.get("/health")
def health(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    failed = db.scalars(
        select(ModelPrediction).where(ModelPrediction.status == PredictionStatus.FAILED).order_by(ModelPrediction.id.desc()).limit(10)
    ).all()
    from app.core.db import database_status

    schema = database_status()
    return {
        "database": db_ok,
        "schema_ready": schema["schema_ready"],
        "missing_tables": schema["missing_tables"],
        "sample_accounts": db.scalar(select(func.count(User.id)).where(User.is_demo.is_(True))),
        "storage": get_storage().healthy(),
        "model": get_model().status(),
        "counts": {
            "users": db.scalar(select(func.count(User.id))),
            "observations": db.scalar(select(func.count(CropObservation.id))),
        },
        "recent_failed_predictions": [
            {"id": p.id, "observation_id": p.observation_id, "reason": p.status_reason, "at": p.created_at} for p in failed
        ],
    }
