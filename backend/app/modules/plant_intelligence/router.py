from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field as PField
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now_utc
from app.core.db import get_db
from app.core.deps import current_user, require_roles
from app.core.errors import NotFound, Unprocessable
from app.core.events import audit
from app.modules.farms.models import CropCycle, CropReference, Farm, Field
from app.modules.farms.service import get_cycle
from app.modules.identity.models import Role, User
from app.modules.pesticide.models import ApplicationStatus, PesticideApplication
from app.modules.monitoring.models import CropObservation, ModelPrediction
from app.modules.plant_intelligence.models import CropCareGuidance, PlantActivity, PlantObservation

router = APIRouter(prefix="/plant-intelligence", tags=["plant intelligence"])


class ObservationIn(BaseModel):
    crop_cycle_id: int
    observed_at: datetime | None = None
    growth_stage: str | None = PField(default=None, max_length=80)
    height_cm: float | None = PField(default=None, ge=0, le=100000)
    measurements: dict[str, float | None] = PField(default_factory=dict)
    measurement_source: Literal["manual", "sensor", "weather", "model_estimate"] = "manual"
    notes: str | None = PField(default=None, max_length=2000)


class ActivityIn(BaseModel):
    crop_cycle_id: int
    occurred_at: datetime | None = None
    activity_type: Literal["watering", "fertilizer", "pesticide", "pruning", "inspection", "other"]
    description: str = PField(min_length=1, max_length=500)
    quantity: float | None = PField(default=None, ge=0, le=1e9)
    unit: str | None = PField(default=None, max_length=40)
    source: Literal["manual", "agastya_record", "sensor"] = "manual"
    source_record_id: int | None = None


def _cycle_context(c: CropCycle) -> dict:
    return {
        "id": c.id, "crop": c.crop.name, "crop_code": c.crop.code,
        "stage": c.current_stage, "sowing_date": c.sowing_date.isoformat(),
        "field": c.field.name, "farm": c.field.farm.name,
        "district": c.field.farm.district, "timezone": c.field.farm.timezone,
    }


def _owned_cycle(db: Session, user: User, cycle_id: int, *, write: bool = False) -> CropCycle:
    if user.role not in {Role.FARMER.value, Role.ADMIN.value, Role.REVIEWER.value}:
        raise NotFound("Crop record not found.")
    return get_cycle(db, user, cycle_id, write=write, extra_read_roles={Role.REVIEWER.value})


@router.get("/crops")
def list_crops(db: Session = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(CropCycle).join(Field, CropCycle.field_id == Field.id).join(Farm, Field.farm_id == Farm.id).order_by(Farm.name, Field.name)
    if user.role == Role.FARMER:
        stmt = stmt.where(Farm.organization_id == user.organization_id)
    elif user.role not in {Role.ADMIN.value, Role.REVIEWER.value}:
        return {"items": []}
    return {"items": [_cycle_context(c) for c in db.scalars(stmt).unique().all()]}


@router.get("/crops/{cycle_id}/timeline")
def timeline(cycle_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    cycle = _owned_cycle(db, user, cycle_id)
    observations = db.scalars(select(PlantObservation).where(PlantObservation.crop_cycle_id == cycle_id).order_by(PlantObservation.observed_at.desc(), PlantObservation.id.desc())).all()
    activities = db.scalars(select(PlantActivity).where(PlantActivity.crop_cycle_id == cycle_id).order_by(PlantActivity.occurred_at.desc(), PlantActivity.id.desc())).all()
    pesticide_rows = db.scalars(
        select(PesticideApplication)
        .where(PesticideApplication.crop_cycle_id == cycle_id, PesticideApplication.status == ApplicationStatus.ACTIVE.value)
        .order_by(PesticideApplication.applied_at.desc(), PesticideApplication.id.desc())
    ).all()
    activity_items = [{
        "id": a.id, "occurred_at": a.occurred_at.isoformat(), "activity_type": a.activity_type,
        "description": a.description, "quantity": a.quantity, "unit": a.unit,
        "source": a.source, "source_record_id": a.source_record_id, "created_at": a.created_at.isoformat(),
    } for a in activities]
    # Read existing pesticide applications from their source-of-truth table; do not copy or reinterpret them.
    activity_items.extend({
        "id": -app.id, "occurred_at": app.applied_at.isoformat(), "activity_type": "pesticide",
        "description": f"{app.product.trade_name} · {app.dose_value} {app.dose_unit}" + (f" · {app.notes}" if app.notes else ""),
        "quantity": float(app.dose_value), "unit": app.dose_unit, "source": "agastya_record",
        "source_record_id": app.id, "created_at": app.created_at.isoformat(),
    } for app in pesticide_rows)
    activity_items.sort(key=lambda item: item["occurred_at"], reverse=True)
    return {
        "crop": _cycle_context(cycle),
        "observations": [{
            "id": o.id, "observed_at": o.observed_at.isoformat(), "growth_stage": o.growth_stage,
            "height_cm": o.height_cm, "measurements": o.measurements or {},
            "measurement_source": o.measurement_source, "notes": o.notes, "created_at": o.created_at.isoformat(),
        } for o in observations],
        "activities": activity_items,
    }


@router.post("/observations", status_code=201)
def create_observation(payload: ObservationIn, db: Session = Depends(get_db), user: User = Depends(require_roles(Role.FARMER))):
    cycle = _owned_cycle(db, user, payload.crop_cycle_id, write=True)
    observed_at = payload.observed_at or now_utc()
    if observed_at.tzinfo is None:
        raise Unprocessable("Observation time must include a time zone.")
    if observed_at > now_utc():
        raise Unprocessable("Observation time cannot be in the future.")
    if len(payload.measurements) > 30 or any(not k.strip() or len(k) > 60 for k in payload.measurements):
        raise Unprocessable("Measurements contain an invalid key or too many values.")
    row = PlantObservation(crop_cycle_id=cycle.id, created_by=user.id, observed_at=observed_at,
        growth_stage=payload.growth_stage, height_cm=payload.height_cm, measurements=payload.measurements,
        measurement_source=payload.measurement_source, notes=payload.notes)
    db.add(row)
    db.flush()
    audit(db, actor_id=user.id, action="plant_observation.created", entity_type="plant_observation", entity_id=row.id,
          summary="Plant monitoring observation recorded", after={"crop_cycle_id": cycle.id, "source": payload.measurement_source})
    db.commit()
    db.refresh(row)
    return {"id": row.id, "crop_cycle_id": row.crop_cycle_id, "observed_at": row.observed_at.isoformat(),
        "growth_stage": row.growth_stage, "height_cm": row.height_cm, "measurements": row.measurements,
        "measurement_source": row.measurement_source, "notes": row.notes}


@router.post("/activities", status_code=201)
def create_activity(payload: ActivityIn, db: Session = Depends(get_db), user: User = Depends(require_roles(Role.FARMER))):
    cycle = _owned_cycle(db, user, payload.crop_cycle_id, write=True)
    occurred_at = payload.occurred_at or now_utc()
    if occurred_at.tzinfo is None:
        raise Unprocessable("Activity time must include a time zone.")
    if occurred_at > now_utc():
        raise Unprocessable("Activity time cannot be in the future.")
    if payload.source == "agastya_record":
        # A source record ID is required to prevent untraceable claims of synchronized data.
        if payload.source_record_id is None:
            raise Unprocessable("A source record ID is required for linked AGASTYA activities.")
        existing = db.scalar(select(PlantActivity.id).where(
            PlantActivity.crop_cycle_id == cycle.id,
            PlantActivity.source == "agastya_record",
            PlantActivity.source_record_id == payload.source_record_id,
            PlantActivity.activity_type == payload.activity_type))
        if existing:
            return {"id": existing, "duplicate": True}
    row = PlantActivity(crop_cycle_id=cycle.id, created_by=user.id, occurred_at=occurred_at,
        activity_type=payload.activity_type, description=payload.description, quantity=payload.quantity,
        unit=payload.unit, source=payload.source, source_record_id=payload.source_record_id)
    db.add(row)
    db.flush()
    audit(db, actor_id=user.id, action="plant_activity.created", entity_type="plant_activity", entity_id=row.id,
          summary="Plant activity recorded", after={"crop_cycle_id": cycle.id, "activity_type": payload.activity_type, "source": payload.source})
    db.commit()
    db.refresh(row)
    return {"id": row.id, "crop_cycle_id": row.crop_cycle_id, "occurred_at": row.occurred_at.isoformat(),
        "activity_type": row.activity_type, "description": row.description, "quantity": row.quantity,
        "unit": row.unit, "source": row.source, "source_record_id": row.source_record_id}


class GuidanceIn(BaseModel):
    soil_moisture_min_pct: float | None = PField(default=None, ge=0, le=100)
    sunlight_min_hours: float | None = PField(default=None, ge=0, le=24)
    fertilizer_guidance: str | None = PField(default=None, max_length=2000)
    disease_guidance: str | None = PField(default=None, max_length=2000)
    source_reference: str = PField(min_length=3, max_length=500)




@router.get("/guidance")
def list_crop_guidance(db: Session = Depends(get_db), user: User = Depends(require_roles(Role.ADMIN))):
    rows = db.scalars(select(CropCareGuidance).order_by(CropCareGuidance.crop_id)).all()
    return {"items": [{
        "crop_id": row.crop_id, "soil_moisture_min_pct": row.soil_moisture_min_pct,
        "sunlight_min_hours": row.sunlight_min_hours, "fertilizer_guidance": row.fertilizer_guidance,
        "disease_guidance": row.disease_guidance, "source_reference": row.source_reference,
        "verified": True, "updated_at": row.updated_at.isoformat()
    } for row in rows]}


@router.put("/guidance/{crop_id}")
def save_crop_guidance(crop_id: int, payload: GuidanceIn, db: Session = Depends(get_db), user: User = Depends(require_roles(Role.ADMIN))):
    crop = db.get(CropReference, crop_id)
    if not crop:
        raise NotFound("Crop reference not found.")
    row = db.scalar(select(CropCareGuidance).where(CropCareGuidance.crop_id == crop_id))
    before = None
    if row:
        before = {"soil_moisture_min_pct": row.soil_moisture_min_pct, "sunlight_min_hours": row.sunlight_min_hours,
                  "source_reference": row.source_reference}
        for key, value in payload.model_dump().items():
            setattr(row, key, value)
        row.verified_by = user.id
        row.updated_at = now_utc()
    else:
        row = CropCareGuidance(crop_id=crop_id, verified_by=user.id, **payload.model_dump())
        db.add(row)
    db.flush()
    audit(db, actor_id=user.id, action="plant_guidance.updated", entity_type="crop_care_guidance", entity_id=row.id,
          summary=f"Crop care guidance updated for {crop.name}", before=before,
          after={"soil_moisture_min_pct": row.soil_moisture_min_pct, "sunlight_min_hours": row.sunlight_min_hours,
                 "source_reference": row.source_reference})
    db.commit()
    return {"crop_id": crop_id, "soil_moisture_min_pct": row.soil_moisture_min_pct,
            "sunlight_min_hours": row.sunlight_min_hours, "fertilizer_guidance": row.fertilizer_guidance,
            "disease_guidance": row.disease_guidance, "source_reference": row.source_reference,
            "verified": True}


@router.get("/crops/{cycle_id}/recommendations")
def recommendations(cycle_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    cycle = _owned_cycle(db, user, cycle_id)
    guidance = db.scalar(select(CropCareGuidance).where(CropCareGuidance.crop_id == cycle.crop_id))
    latest = db.scalar(select(PlantObservation).where(PlantObservation.crop_cycle_id == cycle_id).order_by(PlantObservation.observed_at.desc(), PlantObservation.id.desc()))
    latest_ai = db.scalar(
        select(ModelPrediction)
        .join(CropObservation, ModelPrediction.observation_id == CropObservation.id)
        .where(CropObservation.crop_cycle_id == cycle_id, ModelPrediction.status == "completed")
        .order_by(ModelPrediction.created_at.desc(), ModelPrediction.id.desc())
    )
    items = []
    measured = latest.measurements if latest else {}
    if guidance and latest:
        moisture = measured.get("soil_moisture_pct")
        if isinstance(moisture, (int, float)) and guidance.soil_moisture_min_pct is not None and moisture < guidance.soil_moisture_min_pct:
            items.append({"type": "water", "priority": "review", "title": "Review irrigation", "reason": f"Recorded soil moisture ({moisture:g}%) is below the configured crop threshold ({guidance.soil_moisture_min_pct:g}%).", "evidence": "manual or sensor observation", "source_reference": guidance.source_reference})
        sunlight = measured.get("sunlight_hours")
        if isinstance(sunlight, (int, float)) and guidance.sunlight_min_hours is not None and sunlight < guidance.sunlight_min_hours:
            items.append({"type": "light", "priority": "review", "title": "Review light exposure", "reason": f"Recorded sunlight ({sunlight:g} hours) is below the configured crop guidance ({guidance.sunlight_min_hours:g} hours).", "evidence": "manual or sensor observation", "source_reference": guidance.source_reference})
    if guidance and guidance.fertilizer_guidance:
        items.append({"type": "fertilizer", "priority": "informational", "title": "Crop-specific fertilizer guidance", "reason": guidance.fertilizer_guidance, "evidence": "administrator-configured guidance", "source_reference": guidance.source_reference})
    if guidance and guidance.disease_guidance and latest_ai and latest_ai.predicted_class and "healthy" not in latest_ai.predicted_class.lower():
        items.append({"type": "plant_health", "priority": "agronomist_review", "title": "Request plant-health review", "reason": guidance.disease_guidance, "evidence": f"Existing model result: {latest_ai.predicted_class}", "source_reference": guidance.source_reference})
    return {"crop_cycle_id": cycle_id, "items": items, "guidance_configured": guidance is not None,
            "latest_observation_id": latest.id if latest else None,
            "message": None if items else "No recommendation is available from the recorded evidence and configured crop guidance."}
