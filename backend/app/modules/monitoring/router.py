from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field as PField, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now_utc
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import current_user, require_roles, reviewer_only
from app.core.errors import NotFound, Unprocessable
from app.core.events import audit
from app.core.pagination import PageParams, paginate
from app.core.storage import get_storage
from app.ml.crop_vision import get_model
from app.modules.farms.models import CropCycle, Farm, Field
from app.modules.farms.service import get_cycle
from app.modules.identity.models import Role, User
from app.modules.monitoring.models import (
    CropObservation,
    HumanReview,
    ReviewDecision,
    ReviewStatus,
)
from app.modules.monitoring.service import create_observation, notify_review, run_inference

router = APIRouter(tags=["crop monitoring"])


def prediction_out(p) -> dict | None:
    if p is None:
        return None
    return {
        "id": p.id,
        "status": p.status,
        "status_reason": p.status_reason,
        "model_key": p.model_key,
        "model_version": p.model_version,
        "predicted_class": p.predicted_class,
        "predicted_crop": p.predicted_crop,
        "predicted_condition": p.predicted_condition,
        "confidence": p.confidence,
        "top_k": p.top_k or [],
        "processing_ms": p.processing_ms,
        "review_recommended": p.review_recommended,
        "created_at": p.created_at,
    }


def review_out(r: HumanReview) -> dict:
    return {
        "id": r.id,
        "decision": r.decision,
        "reviewed_label": r.reviewed_label,
        "notes": r.notes,
        "recommended_action": r.recommended_action,
        "reviewer": r.reviewer.full_name,
        "prediction_id": r.prediction_id,
        "created_at": r.created_at,
    }


def observation_brief(o: CropObservation) -> dict:
    latest = o.predictions[0] if o.predictions else None
    return {
        "id": o.id,
        "crop_cycle_id": o.crop_cycle_id,
        "observed_at": o.observed_at,
        "notes": o.notes,
        "status": o.status,
        "review_status": o.review_status,
        "has_image": o.image_id is not None,
        "prediction": prediction_out(latest),
        "latest_review": review_out(o.reviews[0]) if o.reviews else None,
    }


def _cycle_ctx(c: CropCycle) -> dict:
    return {
        "id": c.id,
        "crop": c.crop.name,
        "crop_code": c.crop.code,
        "vision_supported": c.crop.vision_label_prefix is not None,
        "field": c.field.name,
        "farm": c.field.farm.name,
        "district": c.field.farm.district,
    }


def _get_obs(db: Session, user: User, obs_id: int, *, write: bool = False) -> tuple[CropObservation, CropCycle]:
    o = db.get(CropObservation, obs_id)
    if not o:
        raise NotFound("Observation not found.")
    extra = {Role.REVIEWER.value}
    c = get_cycle(db, user, o.crop_cycle_id, write=write, extra_read_roles=extra)
    return o, c


@router.get("/model-predictions/status")
def model_status(_: User = Depends(current_user)):
    return get_model().status()


@router.post("/observations", status_code=201)
async def upload_observation(
    crop_cycle_id: int = Form(...),
    notes: str | None = Form(None, max_length=1000),
    observed_at: datetime | None = Form(None),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    cycle = get_cycle(db, user, crop_cycle_id, write=True)
    limit = get_settings().max_upload_mb * 1024 * 1024
    raw = await image.read(limit + 1)
    if observed_at and observed_at.tzinfo is None:
        raise Unprocessable("observed_at must include a time zone.")
    if observed_at and observed_at > now_utc():
        raise Unprocessable("Observation time cannot be in the future.")
    obs = create_observation(db, user=user, cycle=cycle, raw=raw, filename=image.filename, notes=notes, observed_at=observed_at)
    db.commit()
    db.refresh(obs)
    return {**observation_brief(obs), "cycle": _cycle_ctx(cycle)}


@router.get("/observations")
def list_observations(
    crop_cycle_id: int | None = None,
    status: str | None = None,
    review_status: str | None = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = (
        select(CropObservation)
        .join(CropCycle, CropObservation.crop_cycle_id == CropCycle.id)
        .join(Field, CropCycle.field_id == Field.id)
        .join(Farm, Field.farm_id == Farm.id)
        .order_by(CropObservation.observed_at.desc(), CropObservation.id.desc())
    )
    if user.role == Role.FARMER:
        stmt = stmt.where(Farm.organization_id == user.organization_id)
    elif user.role not in (Role.REVIEWER, Role.ADMIN):
        return {"items": [], "total": 0, "page": 1, "page_size": params.page_size}
    if crop_cycle_id:
        stmt = stmt.where(CropObservation.crop_cycle_id == crop_cycle_id)
    if status:
        stmt = stmt.where(CropObservation.status == status)
    if review_status:
        stmt = stmt.where(CropObservation.review_status == review_status)

    def mapper(o):
        c = db.get(CropCycle, o.crop_cycle_id)
        return {**observation_brief(o), "cycle": _cycle_ctx(c)}

    return paginate(db, stmt, params, mapper)


@router.get("/observations/{obs_id}")
def get_observation(obs_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    o, c = _get_obs(db, user, obs_id)
    d = observation_brief(o)
    d["cycle"] = _cycle_ctx(c)
    d["predictions"] = [prediction_out(p) for p in o.predictions]
    d["reviews"] = [review_out(r) for r in o.reviews]
    d["image"] = (
        {"width": o.image.width, "height": o.image.height, "size_bytes": o.image.size_bytes, "source_note": o.image.source_note}
        if o.image
        else None
    )
    d["can_review"] = user.role == Role.REVIEWER
    d["can_reanalyze"] = user.role == Role.FARMER
    return d


@router.get("/observations/{obs_id}/image")
def get_observation_image(obs_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    o, _ = _get_obs(db, user, obs_id)
    if not o.image:
        raise NotFound("No image for this observation.")
    try:
        data = get_storage().get(o.image.storage_key)
    except (FileNotFoundError, OSError):
        raise NotFound("Image file is unavailable.")
    return Response(
        content=data,
        media_type=o.image.content_type,
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/observations/{obs_id}/reanalyze")
def reanalyze(obs_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(Role.FARMER))):
    o, c = _get_obs(db, user, obs_id, write=True)
    if not o.image:
        raise Unprocessable("This observation has no image to analyse.")
    data = get_storage().get(o.image.storage_key)
    pred = run_inference(db, o, c, data)
    audit(db, actor_id=user.id, action="observation.reanalyzed", entity_type="crop_observation", entity_id=o.id,
          after={"prediction_status": pred.status})
    db.commit()
    db.refresh(o)
    return get_observation(obs_id, db, user)


# ---------------------------------------------------------------- reviews
class ReviewIn(BaseModel):
    decision: ReviewDecision
    reviewed_label: str | None = PField(default=None, max_length=160)
    notes: str | None = PField(default=None, max_length=2000)
    recommended_action: str | None = PField(default=None, max_length=255)

    @model_validator(mode="after")
    def _label(self):
        if self.decision == ReviewDecision.CORRECTED and not self.reviewed_label:
            raise ValueError("A corrected review needs the reviewer's label.")
        return self


@router.get("/reviews/queue")
def review_queue(
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(reviewer_only),
):
    stmt = (
        select(CropObservation)
        .where(CropObservation.review_status == ReviewStatus.AWAITING)
        .order_by(CropObservation.observed_at.asc())
    )

    def mapper(o):
        return {**observation_brief(o), "cycle": _cycle_ctx(db.get(CropCycle, o.crop_cycle_id))}

    return paginate(db, stmt, params, mapper)


@router.get("/reviews/history")
def review_history(params: PageParams = Depends(), db: Session = Depends(get_db), user: User = Depends(reviewer_only)):
    stmt = select(HumanReview).where(HumanReview.reviewer_id == user.id).order_by(HumanReview.created_at.desc())

    def mapper(r):
        o = db.get(CropObservation, r.observation_id)
        return {**review_out(r), "observation": {**observation_brief(o), "cycle": _cycle_ctx(db.get(CropCycle, o.crop_cycle_id))}}

    return paginate(db, stmt, params, mapper)


@router.post("/observations/{obs_id}/reviews", status_code=201)
def create_review(obs_id: int, body: ReviewIn, db: Session = Depends(get_db), user: User = Depends(reviewer_only)):
    o, _ = _get_obs(db, user, obs_id)
    latest = o.predictions[0] if o.predictions else None
    r = HumanReview(
        observation_id=o.id,
        prediction_id=latest.id if latest else None,
        reviewer_id=user.id,
        **body.model_dump(),
    )
    db.add(r)
    o.review_status = ReviewStatus.REVIEWED
    db.flush()
    audit(db, actor_id=user.id, action="observation.reviewed", entity_type="crop_observation", entity_id=o.id,
          after={"decision": body.decision, "reviewed_label": body.reviewed_label})
    notify_review(db, o, user, body.decision)
    db.commit()
    return review_out(r)
