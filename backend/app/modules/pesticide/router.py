from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field as PField, model_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.clock import now_utc
from app.core.db import get_db
from app.core.deps import admin_only, current_user, farmer_only, require_roles
from app.core.errors import Conflict, NotFound, Unprocessable
from app.core.events import audit
from app.modules.farms.models import CropCycle, CropReference, CycleStatus
from app.modules.farms.service import farmer_cycles_stmt, get_cycle
from app.modules.identity.models import Role, User
from app.modules.pesticide.models import (
    ApplicationStatus,
    HarvestAssessment,
    LabelSource,
    LabelVerification,
    PesticideApplication,
    PesticideProduct,
    ProductLabel,
)
from app.modules.pesticide.service import assessment_out, evaluate_cycle, label_provenance, record_assessment, recompute_for_product

router = APIRouter(tags=["pesticide safety"])


def label_out(l: ProductLabel) -> dict:
    return {
        "id": l.id,
        "product_id": l.product_id,
        "product_name": l.product.trade_name if l.product else None,
        "crop": {"id": l.crop.id, "name": l.crop.name},
        "label_version": l.label_version,
        "phi_days": l.phi_days,
        "dose_min": l.dose_min,
        "dose_max": l.dose_max,
        "dose_unit": l.dose_unit,
        "source_reference": l.source_reference,
        "source_kind": l.source_kind,
        "provenance": label_provenance(l),
        "verification_status": l.verification_status,
        "verified_at": l.verified_at,
        "valid_from": l.valid_from,
        "valid_until": l.valid_until,
        "notes": l.notes,
        "created_at": l.created_at,
    }


def product_out(p: PesticideProduct, crop_id: int | None = None) -> dict:
    labels = [l for l in p.labels if crop_id is None or l.crop_id == crop_id]
    return {
        "id": p.id,
        "trade_name": p.trade_name,
        "active_ingredient": p.active_ingredient,
        "formulation": p.formulation,
        "product_type": p.product_type,
        "registrant": p.registrant,
        "registration_ref": p.registration_ref,
        "labels": [label_out(l) for l in labels],
    }


def application_out(a: PesticideApplication) -> dict:
    return {
        "id": a.id,
        "crop_cycle_id": a.crop_cycle_id,
        "product": {"id": a.product.id, "trade_name": a.product.trade_name, "active_ingredient": a.product.active_ingredient},
        "applied_at": a.applied_at,
        "dose_value": a.dose_value,
        "dose_unit": a.dose_unit,
        "treated_area_ha": a.treated_area_ha,
        "application_method": a.application_method,
        "target_problem": a.target_problem,
        "recorded_phi_days": a.recorded_phi_days,
        "notes": a.notes,
        "status": a.status,
        "void_reason": a.void_reason,
        "voided_at": a.voided_at,
        "recorded_by": a.recorder.full_name if a.recorder else None,
        "created_at": a.created_at,
    }


# ---------------------------------------------------------------- products & labels
@router.get("/pesticide-products")
def list_products(
    q: str | None = Query(None, max_length=80),
    crop_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.FARMER, Role.ADMIN, Role.REVIEWER)),
):
    stmt = select(PesticideProduct).order_by(PesticideProduct.trade_name)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(PesticideProduct.trade_name.ilike(like), PesticideProduct.active_ingredient.ilike(like)))
    return [product_out(p, crop_id) for p in db.scalars(stmt)]


class ProductIn(BaseModel):
    trade_name: str = PField(min_length=2, max_length=120)
    active_ingredient: str | None = PField(default=None, max_length=160)
    formulation: str | None = PField(default=None, max_length=60)
    product_type: str | None = PField(default=None, max_length=40)
    registrant: str | None = PField(default=None, max_length=160)
    registration_ref: str | None = PField(default=None, max_length=120)


@router.post("/pesticide-products", status_code=201)
def create_product(body: ProductIn, db: Session = Depends(get_db), user: User = Depends(require_roles(Role.FARMER, Role.ADMIN))):
    exists = db.scalar(
        select(PesticideProduct).where(
            PesticideProduct.trade_name.ilike(body.trade_name.strip()), PesticideProduct.formulation == body.formulation
        )
    )
    if exists:
        raise Conflict("This product already exists.")
    p = PesticideProduct(**body.model_dump(), created_by=user.id)
    db.add(p)
    db.flush()
    audit(db, actor_id=user.id, action="pesticide_product.created", entity_type="pesticide_product", entity_id=p.id, summary=p.trade_name)
    db.commit()
    db.refresh(p)
    return product_out(p)


class LabelIn(BaseModel):
    crop_id: int
    label_version: str = PField(min_length=1, max_length=60)
    phi_days: int | None = PField(default=None, ge=0, le=365)
    dose_min: float | None = PField(default=None, gt=0)
    dose_max: float | None = PField(default=None, gt=0)
    dose_unit: str | None = PField(default=None, max_length=40)
    source_reference: str = PField(min_length=3, max_length=2000)
    valid_from: date
    valid_until: date | None = None
    notes: str | None = PField(default=None, max_length=2000)

    @model_validator(mode="after")
    def _order(self):
        if self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until must be on or after valid_from.")
        if self.dose_min and self.dose_max and self.dose_max < self.dose_min:
            raise ValueError("Maximum dose must be at least the minimum dose.")
        return self


@router.post("/pesticide-products/{product_id}/labels", status_code=201)
def submit_label(
    product_id: int, body: LabelIn, db: Session = Depends(get_db), user: User = Depends(require_roles(Role.FARMER, Role.ADMIN))
):
    """Submit a candidate label rule. It is always stored UNVERIFIED and does not affect harvest
    eligibility until an administrator verifies it against an authoritative label."""
    p = db.get(PesticideProduct, product_id)
    if not p:
        raise NotFound("Product not found.")
    if not db.get(CropReference, body.crop_id):
        raise Unprocessable("Unknown crop.")
    lbl = ProductLabel(
        product_id=p.id,
        **body.model_dump(),
        source_kind=LabelSource.MANUAL,
        verification_status=LabelVerification.UNVERIFIED,
        submitted_by=user.id,
    )
    db.add(lbl)
    db.flush()
    audit(db, actor_id=user.id, action="label.submitted", entity_type="product_label", entity_id=lbl.id,
          after={"phi_days": lbl.phi_days, "crop_id": lbl.crop_id, "source": lbl.source_reference})
    recompute_for_product(db, p.id, actor_id=user.id, trigger="label_submitted")
    db.commit()
    db.refresh(lbl)
    return label_out(lbl)


@router.get("/pesticide-labels")
def list_labels(
    status: LabelVerification | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    stmt = select(ProductLabel).order_by(ProductLabel.created_at.desc())
    if status:
        stmt = stmt.where(ProductLabel.verification_status == status)
    return [label_out(l) for l in db.scalars(stmt)]


class VerifyIn(BaseModel):
    source_reference: str = PField(min_length=3, max_length=2000)
    phi_days: int = PField(ge=0, le=365)
    valid_from: date
    valid_until: date | None = None
    note: str | None = PField(default=None, max_length=1000)


@router.post("/pesticide-labels/{label_id}/verify")
def verify_label(label_id: int, body: VerifyIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    lbl = db.get(ProductLabel, label_id)
    if not lbl:
        raise NotFound("Label not found.")
    if lbl.verification_status == LabelVerification.VERIFIED:
        raise Conflict("This label is already verified.")
    if body.valid_until and body.valid_until < body.valid_from:
        raise Unprocessable("valid_until must be on or after valid_from.")
    before = {"status": lbl.verification_status, "phi_days": lbl.phi_days, "source": lbl.source_reference}
    lbl.source_reference = body.source_reference
    lbl.phi_days = body.phi_days
    lbl.valid_from = body.valid_from
    lbl.valid_until = body.valid_until
    lbl.verification_status = LabelVerification.VERIFIED
    lbl.verified_by = user.id
    lbl.verified_at = now_utc()
    if body.note:
        lbl.notes = ((lbl.notes or "") + "\nVerification: " + body.note).strip()
    audit(db, actor_id=user.id, action="label.verified", entity_type="product_label", entity_id=lbl.id, before=before,
          after={"status": "verified", "phi_days": lbl.phi_days, "source": lbl.source_reference}, severity="safety")
    n = recompute_for_product(db, lbl.product_id, actor_id=user.id, trigger="label_verified")
    db.commit()
    return {**label_out(lbl), "cycles_recomputed": n}


class RejectIn(BaseModel):
    reason: str = PField(min_length=3, max_length=1000)


@router.post("/pesticide-labels/{label_id}/reject")
def reject_label(label_id: int, body: RejectIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    lbl = db.get(ProductLabel, label_id)
    if not lbl:
        raise NotFound("Label not found.")
    if lbl.verification_status == LabelVerification.REJECTED:
        raise Conflict("This label is already rejected.")
    before = {"status": lbl.verification_status}
    lbl.verification_status = LabelVerification.REJECTED
    lbl.notes = ((lbl.notes or "") + "\nRejected: " + body.reason).strip()
    audit(db, actor_id=user.id, action="label.rejected", entity_type="product_label", entity_id=lbl.id, before=before,
          after={"status": "rejected", "reason": body.reason}, severity="safety")
    recompute_for_product(db, lbl.product_id, actor_id=user.id, trigger="label_rejected")
    db.commit()
    return label_out(lbl)


@router.post("/pesticide-labels/{label_id}/revoke")
def revoke_label(label_id: int, body: RejectIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    """Withdraw a verification (e.g. the label was superseded or entered wrongly). The rule returns to
    UNVERIFIED, stops counting immediately, and can be re-verified after correction. Fully audited."""
    lbl = db.get(ProductLabel, label_id)
    if not lbl:
        raise NotFound("Label not found.")
    if lbl.verification_status != LabelVerification.VERIFIED:
        raise Conflict("Only a verified label rule can have its verification revoked.", code="invalid_transition")
    before = {"status": lbl.verification_status, "verified_by": lbl.verified_by, "verified_at": str(lbl.verified_at)}
    lbl.verification_status = LabelVerification.UNVERIFIED
    lbl.verified_by = None
    lbl.verified_at = None
    lbl.notes = ((lbl.notes or "") + "\nVerification revoked: " + body.reason).strip()
    audit(db, actor_id=user.id, action="label.verification_revoked", entity_type="product_label", entity_id=lbl.id,
          before=before, after={"status": "unverified", "reason": body.reason}, severity="safety")
    n = recompute_for_product(db, lbl.product_id, actor_id=user.id, trigger="label_revoked")
    db.commit()
    return {**label_out(lbl), "cycles_recomputed": n}


# ---------------------------------------------------------------- applications
class ApplicationIn(BaseModel):
    crop_cycle_id: int
    product_id: int
    applied_at: datetime
    dose_value: float = PField(gt=0, le=100000)
    dose_unit: str = PField(min_length=1, max_length=40)
    treated_area_ha: float | None = PField(default=None, gt=0, le=10000)
    application_method: str | None = PField(default=None, max_length=60)
    target_problem: str | None = PField(default=None, max_length=120)
    recorded_phi_days: int | None = PField(default=None, ge=0, le=365)
    notes: str | None = PField(default=None, max_length=2000)

    @model_validator(mode="after")
    def _tz(self):
        if self.applied_at.tzinfo is None:
            raise ValueError("applied_at must include a time zone offset.")
        return self


@router.get("/applications")
def list_applications(
    crop_cycle_id: int | None = None,
    include_voided: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(farmer_only),
):
    cycles = farmer_cycles_stmt(user).with_only_columns(CropCycle.id)
    stmt = select(PesticideApplication).where(PesticideApplication.crop_cycle_id.in_(cycles)).order_by(
        PesticideApplication.applied_at.desc()
    )
    if crop_cycle_id:
        get_cycle(db, user, crop_cycle_id)
        stmt = stmt.where(PesticideApplication.crop_cycle_id == crop_cycle_id)
    if not include_voided:
        stmt = stmt.where(PesticideApplication.status == ApplicationStatus.ACTIVE)
    return [application_out(a) for a in db.scalars(stmt)]


@router.post("/applications", status_code=201)
def create_application(body: ApplicationIn, db: Session = Depends(get_db), user: User = Depends(farmer_only)):
    cycle = get_cycle(db, user, body.crop_cycle_id, write=True)
    if cycle.status == CycleStatus.CLOSED:
        raise Conflict("This crop cycle is closed.")
    product = db.get(PesticideProduct, body.product_id)
    if not product:
        raise Unprocessable("Unknown product.")
    if body.applied_at > now_utc() + timedelta(minutes=5):
        raise Unprocessable("Application time cannot be in the future. Record applications after they happen.")
    if body.applied_at.date() < cycle.sowing_date - timedelta(days=30):
        raise Unprocessable("Application date is long before this cycle's sowing date.")
    if body.treated_area_ha and body.treated_area_ha > float(cycle.field.area_ha) * 1.05:
        raise Unprocessable("Treated area is larger than the field.")
    a = PesticideApplication(**body.model_dump(), recorded_by=user.id, status=ApplicationStatus.ACTIVE)
    db.add(a)
    db.flush()
    audit(db, actor_id=user.id, action="application.recorded", entity_type="pesticide_application", entity_id=a.id,
          after={"product": product.trade_name, "applied_at": body.applied_at.isoformat(), "dose": f"{body.dose_value} {body.dose_unit}"},
          severity="safety")
    result, _ = record_assessment(db, cycle, trigger="application_recorded", actor_id=user.id)
    db.commit()
    db.refresh(a)
    return {"application": application_out(a), "assessment": assessment_out(result)}


class VoidIn(BaseModel):
    reason: str = PField(min_length=5, max_length=255)


@router.post("/applications/{app_id}/void")
def void_application(app_id: int, body: VoidIn, db: Session = Depends(get_db), user: User = Depends(farmer_only)):
    a = db.get(PesticideApplication, app_id)
    if not a:
        raise NotFound("Application not found.")
    cycle = get_cycle(db, user, a.crop_cycle_id, write=True)
    if a.status == ApplicationStatus.VOIDED:
        raise Conflict("This application record is already voided.")
    a.status = ApplicationStatus.VOIDED
    a.voided_by = user.id
    a.voided_at = now_utc()
    a.void_reason = body.reason
    audit(db, actor_id=user.id, action="application.voided", entity_type="pesticide_application", entity_id=a.id,
          before={"status": "active"}, after={"status": "voided", "reason": body.reason}, severity="safety")
    result, _ = record_assessment(db, cycle, trigger="application_voided", actor_id=user.id)
    db.commit()
    return {"application": application_out(a), "assessment": assessment_out(result)}


# ---------------------------------------------------------------- harvest assessments
def _cycle_ref(c: CropCycle) -> dict:
    return {"id": c.id, "crop": c.crop.name, "field": c.field.name, "farm": c.field.farm.name,
            "expected_harvest_date": c.expected_harvest_date, "status": c.status, "current_stage": c.current_stage}


@router.get("/harvest-assessments")
def harvest_overview(db: Session = Depends(get_db), user: User = Depends(farmer_only)):
    """Live eligibility for every open crop cycle (computed now, not cached)."""
    out = []
    for c in db.scalars(farmer_cycles_stmt(user).where(CropCycle.status != CycleStatus.CLOSED).order_by(CropCycle.id)):
        res = evaluate_cycle(db, c)
        out.append({"cycle": _cycle_ref(c), "assessment": assessment_out(res), "application_count": len(res.outcomes)})
    order = {"restricted": 0, "unknown": 1, "upcoming": 2, "eligible": 3}
    out.sort(key=lambda x: (order[x["assessment"]["status"]], x["cycle"]["id"]))
    return out


@router.get("/harvest-assessments/{cycle_id}")
def harvest_for_cycle(cycle_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = get_cycle(db, user, cycle_id)
    res = evaluate_cycle(db, c)
    history = db.scalars(
        select(HarvestAssessment).where(HarvestAssessment.crop_cycle_id == c.id).order_by(HarvestAssessment.id.desc()).limit(20)
    ).all()
    apps = db.scalars(
        select(PesticideApplication).where(PesticideApplication.crop_cycle_id == c.id).order_by(PesticideApplication.applied_at.desc())
    ).all()
    return {
        "cycle": _cycle_ref(c),
        "assessment": assessment_out(res),
        "applications": [application_out(a) for a in apps],
        "history": [
            {
                "id": h.id,
                "status": h.status,
                "earliest_eligible_date": h.earliest_eligible_date,
                "unresolved_count": h.unresolved_count,
                "trigger": h.trigger,
                "created_at": h.created_at,
                "rule_version": h.rule_version,
            }
            for h in history
        ],
    }
