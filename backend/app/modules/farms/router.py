from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field as PField, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import local_today, now_utc
from app.core.db import get_db
from app.core.deps import current_user, farmer_only
from app.core.errors import Conflict, NotFound, Unprocessable
from app.core.events import audit
from app.modules.farms.models import CropCycle, CropReference, CycleStatus, Farm, Field, GrowthStageRecord
from app.modules.farms.service import farmer_cycles_stmt, get_cycle, get_farm, get_field
from app.modules.identity.models import Role, User

router = APIRouter(tags=["farms"])


# ---------------------------------------------------------------- schemas / serialisers
class CropOut(BaseModel):
    id: int
    code: str
    name: str
    scientific_name: str | None
    category: str
    growth_stages: list[str]
    pollinator_dependent: bool
    vision_supported: bool


def crop_out(c: CropReference) -> CropOut:
    return CropOut(
        id=c.id,
        code=c.code,
        name=c.name,
        scientific_name=c.scientific_name,
        category=c.category,
        growth_stages=list(c.growth_stages or []),
        pollinator_dependent=c.pollinator_dependent,
        vision_supported=c.vision_label_prefix is not None,
    )


def field_out(f: Field, include_cycles: bool = True) -> dict:
    d = {
        "id": f.id,
        "farm_id": f.farm_id,
        "name": f.name,
        "area_ha": f.area_ha,
        "soil_type": f.soil_type,
        "irrigation": f.irrigation,
    }
    if include_cycles:
        d["cycles"] = [cycle_brief(c) for c in f.cycles]
    return d


def farm_out(f: Farm, include_fields: bool = False) -> dict:
    d = {
        "id": f.id,
        "name": f.name,
        "village": f.village,
        "district": f.district,
        "state": f.state,
        "timezone": f.timezone,
        "latitude": f.latitude,
        "longitude": f.longitude,
        "field_count": len(f.fields),
        "total_area_ha": round(sum(x.area_ha for x in f.fields), 2),
        "active_cycle_count": sum(1 for x in f.fields for c in x.cycles if c.status != CycleStatus.CLOSED),
    }
    if include_fields:
        d["fields"] = [field_out(x) for x in f.fields]
    return d


def cycle_brief(c: CropCycle) -> dict:
    return {
        "id": c.id,
        "crop": {"id": c.crop.id, "name": c.crop.name, "code": c.crop.code},
        "variety": c.variety,
        "season": c.season,
        "status": c.status,
        "current_stage": c.current_stage,
        "sowing_date": c.sowing_date,
        "expected_flowering_start": c.expected_flowering_start,
        "expected_flowering_end": c.expected_flowering_end,
        "expected_harvest_date": c.expected_harvest_date,
        "field": {"id": c.field.id, "name": c.field.name, "area_ha": c.field.area_ha},
        "farm": {"id": c.field.farm.id, "name": c.field.farm.name, "district": c.field.farm.district},
    }


# ---------------------------------------------------------------- reference data
@router.get("/crops", response_model=list[CropOut])
def list_crops(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [crop_out(c) for c in db.scalars(select(CropReference).order_by(CropReference.name))]


# ---------------------------------------------------------------- farms
class FarmIn(BaseModel):
    name: str = PField(min_length=2, max_length=120)
    village: str | None = PField(default=None, max_length=80)
    district: str = PField(min_length=2, max_length=80)
    state: str = PField(min_length=2, max_length=80)
    timezone: str = PField(default="Asia/Kolkata", max_length=64)
    latitude: float | None = PField(default=None, ge=-90, le=90)
    longitude: float | None = PField(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _coords(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Provide both latitude and longitude, or neither.")
        from zoneinfo import ZoneInfo

        try:
            ZoneInfo(self.timezone)
        except Exception as exc:
            raise ValueError("Unknown time zone.") from exc
        return self


@router.get("/farms")
def list_farms(db: Session = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(Farm).order_by(Farm.name)
    if user.role == Role.FARMER:
        stmt = stmt.where(Farm.organization_id == user.organization_id)
    elif user.role != Role.ADMIN:
        return []
    return [farm_out(f) for f in db.scalars(stmt)]


@router.post("/farms", status_code=201)
def create_farm(body: FarmIn, db: Session = Depends(get_db), user: User = Depends(farmer_only)):
    farm = Farm(organization_id=user.organization_id, **body.model_dump())
    if body.latitude is not None:
        farm.location_source = "entered by farmer"
    db.add(farm)
    db.flush()
    audit(db, actor_id=user.id, action="farm.created", entity_type="farm", entity_id=farm.id, summary=farm.name)
    db.commit()
    return farm_out(farm, include_fields=True)


@router.get("/farms/{farm_id}")
def farm_detail(farm_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return farm_out(get_farm(db, user, farm_id), include_fields=True)


@router.patch("/farms/{farm_id}")
def update_farm(farm_id: int, body: FarmIn, db: Session = Depends(get_db), user: User = Depends(farmer_only)):
    farm = get_farm(db, user, farm_id, write=True)
    for k, v in body.model_dump().items():
        setattr(farm, k, v)
    db.commit()
    return farm_out(farm, include_fields=True)


class FieldIn(BaseModel):
    name: str = PField(min_length=1, max_length=80)
    area_ha: float = PField(gt=0, le=10000)
    soil_type: str | None = PField(default=None, max_length=60)
    irrigation: str | None = PField(default=None, max_length=60)


@router.post("/farms/{farm_id}/fields", status_code=201)
def create_field(farm_id: int, body: FieldIn, db: Session = Depends(get_db), user: User = Depends(farmer_only)):
    farm = get_farm(db, user, farm_id, write=True)
    if any(f.name.lower() == body.name.lower() for f in farm.fields):
        raise Conflict("A field with this name already exists on this farm.")
    field = Field(farm_id=farm.id, **body.model_dump())
    db.add(field)
    db.flush()
    audit(db, actor_id=user.id, action="field.created", entity_type="field", entity_id=field.id, summary=field.name)
    db.commit()
    db.refresh(field)
    return field_out(field)


@router.patch("/fields/{field_id}")
def update_field(field_id: int, body: FieldIn, db: Session = Depends(get_db), user: User = Depends(farmer_only)):
    field = get_field(db, user, field_id, write=True)
    for k, v in body.model_dump().items():
        setattr(field, k, v)
    db.commit()
    return field_out(field)


# ---------------------------------------------------------------- crop cycles
class CycleIn(BaseModel):
    field_id: int
    crop_id: int
    variety: str | None = PField(default=None, max_length=80)
    season: str | None = PField(default=None, max_length=40)
    sowing_date: date
    expected_flowering_start: date | None = None
    expected_flowering_end: date | None = None
    expected_harvest_date: date | None = None
    current_stage: str | None = PField(default=None, max_length=60)

    @model_validator(mode="after")
    def _dates(self):
        fs, fe = self.expected_flowering_start, self.expected_flowering_end
        if (fs is None) != (fe is None):
            raise ValueError("Provide both flowering start and end dates, or neither.")
        if fs and fe and fe < fs:
            raise ValueError("Flowering end must be on or after flowering start.")
        if fs and fs < self.sowing_date:
            raise ValueError("Flowering cannot start before sowing.")
        if self.expected_harvest_date and self.expected_harvest_date < self.sowing_date:
            raise ValueError("Expected harvest must be after sowing.")
        return self


class CycleUpdate(BaseModel):
    variety: str | None = PField(default=None, max_length=80)
    expected_flowering_start: date | None = None
    expected_flowering_end: date | None = None
    expected_harvest_date: date | None = None
    status: CycleStatus | None = None

    @model_validator(mode="after")
    def _dates(self):
        fs, fe = self.expected_flowering_start, self.expected_flowering_end
        if fs and fe and fe < fs:
            raise ValueError("Flowering end must be on or after flowering start.")
        return self


@router.get("/crop-cycles")
def list_cycles(
    status: str | None = Query(None),
    crop_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(farmer_only),
):
    stmt = farmer_cycles_stmt(user).order_by(CropCycle.sowing_date.desc())
    if status == "open":
        stmt = stmt.where(CropCycle.status != CycleStatus.CLOSED)
    elif status:
        stmt = stmt.where(CropCycle.status == status)
    if crop_id:
        stmt = stmt.where(CropCycle.crop_id == crop_id)
    return [cycle_brief(c) for c in db.scalars(stmt)]


@router.post("/crop-cycles", status_code=201)
def create_cycle(body: CycleIn, db: Session = Depends(get_db), user: User = Depends(farmer_only)):
    field = get_field(db, user, body.field_id, write=True)
    crop = db.get(CropReference, body.crop_id)
    if not crop:
        raise Unprocessable("Unknown crop.")
    if any(c.status in (CycleStatus.ACTIVE, CycleStatus.HARVESTING) for c in field.cycles):
        raise Conflict("This field already has an active crop cycle. Close it before starting another.")
    if body.current_stage and body.current_stage not in (crop.growth_stages or []):
        raise Unprocessable("Unknown growth stage for this crop.")
    today = local_today(field.farm.timezone)
    status = CycleStatus.PLANNED if body.sowing_date > today else CycleStatus.ACTIVE
    cycle = CropCycle(**body.model_dump(), status=status, created_by=user.id)
    db.add(cycle)
    db.flush()
    if body.current_stage and body.sowing_date <= today:
        db.add(GrowthStageRecord(crop_cycle_id=cycle.id, stage=body.current_stage, observed_on=today, recorded_by=user.id))
    audit(db, actor_id=user.id, action="crop_cycle.created", entity_type="crop_cycle", entity_id=cycle.id,
          summary=f"{crop.name} on {field.name}")
    db.commit()
    db.refresh(cycle)
    return cycle_brief(cycle)


@router.get("/crop-cycles/{cycle_id}")
def cycle_detail(cycle_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = get_cycle(db, user, cycle_id, extra_read_roles={Role.REVIEWER.value})
    d = cycle_brief(c)
    d["growth_stages"] = list(c.crop.growth_stages or [])
    d["vision_supported"] = c.crop.vision_label_prefix is not None
    d["pollinator_dependent"] = c.crop.pollinator_dependent
    d["farm"]["timezone"] = c.field.farm.timezone
    d["stage_records"] = [
        {"id": s.id, "stage": s.stage, "observed_on": s.observed_on, "notes": s.notes}
        for s in db.scalars(
            select(GrowthStageRecord).where(GrowthStageRecord.crop_cycle_id == c.id).order_by(GrowthStageRecord.observed_on.desc())
        )
    ]
    return d


@router.patch("/crop-cycles/{cycle_id}")
def update_cycle(cycle_id: int, body: CycleUpdate, db: Session = Depends(get_db), user: User = Depends(farmer_only)):
    c = get_cycle(db, user, cycle_id, write=True)
    before = {"status": c.status, "flowering": [str(c.expected_flowering_start), str(c.expected_flowering_end)]}
    data = body.model_dump(exclude_unset=True)
    fs = data.get("expected_flowering_start", c.expected_flowering_start)
    fe = data.get("expected_flowering_end", c.expected_flowering_end)
    if fs and fe and fe < fs:
        raise Unprocessable("Flowering end must be on or after flowering start.")
    if fs and fs < c.sowing_date:
        raise Unprocessable("Flowering cannot start before sowing.")
    if "status" in data and data["status"] is not None:
        allowed = {
            CycleStatus.PLANNED: {CycleStatus.ACTIVE, CycleStatus.CLOSED},
            CycleStatus.ACTIVE: {CycleStatus.HARVESTING, CycleStatus.CLOSED},
            CycleStatus.HARVESTING: {CycleStatus.CLOSED},
            CycleStatus.CLOSED: set(),
        }
        if data["status"] != c.status and data["status"] not in allowed[CycleStatus(c.status)]:
            raise Conflict(f"A cycle cannot move from {c.status} to {data['status']}.", code="invalid_transition")
        if data["status"] == CycleStatus.CLOSED:
            c.closed_at = now_utc()
    for k, v in data.items():
        setattr(c, k, v)
    audit(db, actor_id=user.id, action="crop_cycle.updated", entity_type="crop_cycle", entity_id=c.id, before=before,
          after={"status": c.status, "flowering": [str(c.expected_flowering_start), str(c.expected_flowering_end)]})
    db.commit()
    return cycle_detail(cycle_id, db, user)


class StageIn(BaseModel):
    stage: str = PField(min_length=1, max_length=60)
    observed_on: date
    notes: str | None = PField(default=None, max_length=1000)


@router.post("/crop-cycles/{cycle_id}/stages", status_code=201)
def add_stage(cycle_id: int, body: StageIn, db: Session = Depends(get_db), user: User = Depends(farmer_only)):
    c = get_cycle(db, user, cycle_id, write=True)
    if body.stage not in (c.crop.growth_stages or []):
        raise Unprocessable("Unknown growth stage for this crop.")
    today = local_today(c.field.farm.timezone)
    if body.observed_on > today:
        raise Unprocessable("Stage date cannot be in the future.")
    if body.observed_on < c.sowing_date:
        raise Unprocessable("Stage date cannot be before sowing.")
    rec = GrowthStageRecord(crop_cycle_id=c.id, recorded_by=user.id, **body.model_dump())
    db.add(rec)
    latest = db.scalar(
        select(GrowthStageRecord.observed_on).where(GrowthStageRecord.crop_cycle_id == c.id).order_by(GrowthStageRecord.observed_on.desc()).limit(1)
    )
    if latest is None or body.observed_on >= latest:
        c.current_stage = body.stage
    db.commit()
    return {"id": rec.id, "stage": rec.stage, "observed_on": rec.observed_on, "notes": rec.notes}


@router.get("/crop-cycles/{cycle_id}/timeline")
def cycle_timeline(cycle_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Chronological crop history: stage updates, observations (with model result + reviews), applications, bookings."""
    from app.modules.monitoring.models import CropObservation
    from app.modules.monitoring.router import observation_brief
    from app.modules.pesticide.models import PesticideApplication
    from app.modules.pollination.models import PollinationBooking

    c = get_cycle(db, user, cycle_id, extra_read_roles={Role.REVIEWER.value})
    items: list[dict] = []
    for s in db.scalars(select(GrowthStageRecord).where(GrowthStageRecord.crop_cycle_id == c.id)):
        items.append({"kind": "stage", "date": s.observed_on.isoformat(), "stage": s.stage, "notes": s.notes, "id": s.id})
    for o in db.scalars(select(CropObservation).where(CropObservation.crop_cycle_id == c.id)):
        items.append({"kind": "observation", "date": o.observed_at.isoformat(), **observation_brief(o)})
        for r in o.reviews:
            items.append({"kind": "review", "date": r.created_at.isoformat(), "observation_id": o.id, "decision": r.decision,
                          "reviewed_label": r.reviewed_label, "reviewer": r.reviewer.full_name, "id": r.id})
    for a in db.scalars(select(PesticideApplication).where(PesticideApplication.crop_cycle_id == c.id)):
        items.append({"kind": "application", "date": a.applied_at.isoformat(), "id": a.id, "product": a.product.trade_name,
                      "status": a.status, "dose": f"{a.dose_value:g} {a.dose_unit}"})
    for b in db.scalars(select(PollinationBooking).where(PollinationBooking.crop_cycle_id == c.id)):
        items.append({"kind": "booking", "date": b.created_at.isoformat(), "id": b.id, "status": b.status,
                      "provider": b.provider.display_name, "start_date": b.start_date.isoformat(), "end_date": b.end_date.isoformat()})
    items.append({"kind": "sowing", "date": c.sowing_date.isoformat(), "id": c.id})
    items.sort(key=lambda x: x["date"], reverse=True)
    return items


@router.get("/crop-cycles/{cycle_id}/stages")
def list_stages(cycle_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = get_cycle(db, user, cycle_id, extra_read_roles={Role.REVIEWER.value})
    if not c:
        raise NotFound("Not found")
    return cycle_detail(cycle_id, db, user)["stage_records"]
