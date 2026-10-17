from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field as PField, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import local_today, now_utc
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import buyer_only, current_user, farmer_only, require_roles
from app.core.errors import Conflict, InvalidTransition, NotFound, Unprocessable
from app.core.events import audit
from app.core.idempotency import run_idempotent
from app.modules.farms.models import CropCycle, CropReference
from app.modules.farms.service import get_cycle
from app.modules.identity.models import Role, User
from app.modules.pesticide.service import evaluate_for_harvest_date
from app.modules.produce import ranking
from app.modules.produce.models import (
    GRADES,
    UNITS_TO_KG,
    AssignmentStatus,
    BatchAssignment,
    BatchStatus,
    BuyerDemand,
    BuyerMatch,
    BuyerProfile,
    DemandStatus,
    ProduceBatch,
    RerouteRun,
    RerouteTrigger,
    Shipment,
    ShipmentStatus,
)
from app.modules.produce.service import (
    active_assignment,
    advance_shipment,
    allocated_kg,
    batch_tz,
    batch_view,
    buyer_cancel,
    confirm_destination,
    remaining_kg,
    start_reroute,
)

router = APIRouter(tags=["produce"])


def _f(v):
    return float(v) if v is not None else None


def shipment_out(s: Shipment | None) -> dict | None:
    if s is None:
        return None
    return {
        "id": s.id,
        "status": s.status,
        "scheduled_date": s.scheduled_date,
        "events": [{"status": e.status, "note": e.note, "at": e.created_at} for e in s.events],
    }


def assignment_out(a: BatchAssignment) -> dict:
    return {
        "id": a.id,
        "buyer": {"id": a.buyer.id, "display_name": a.buyer.display_name, "district": a.buyer.district, "buyer_type": a.buyer.buyer_type},
        "demand_id": a.demand_id,
        "quantity_kg": _f(a.quantity_kg),
        "status": a.status,
        "reason": a.reason,
        "assigned_at": a.assigned_at,
        "ended_at": a.ended_at,
        "end_reason": a.end_reason,
        "shipment": shipment_out(a.shipment),
    }


def batch_out(b: ProduceBatch, detail: bool = False) -> dict:
    tz = batch_tz(b)
    today = local_today(tz)
    bv = batch_view(b)
    urg, days_left = ranking.urgency(bv, today)
    sb = ranking.sell_by(bv)
    cur = active_assignment(b)
    d = {
        "id": b.id,
        "code": b.code,
        "crop": {"id": b.crop.id, "name": b.crop.name},
        "crop_cycle_id": b.crop_cycle_id,
        "source": (
            {"field": b.crop_cycle.field.name, "farm": b.crop_cycle.field.farm.name, "district": b.crop_cycle.field.farm.district}
            if b.crop_cycle
            else None
        ),
        "quantity_value": _f(b.quantity_value),
        "unit": b.unit,
        "quantity_kg": _f(b.quantity_kg),
        "grade": b.grade,
        "quality_notes": b.quality_notes,
        "harvested_on": b.harvested_on,
        "shelf_life_days": b.shelf_life_days,
        "shelf_life_source": b.shelf_life_source,
        "storage_condition": b.storage_condition,
        "available_from": b.available_from,
        "deliver_by": b.deliver_by,
        "sell_by": sb,
        "days_left": days_left,
        "urgency": urg,
        "status": b.status,
        "harvest_check_status": b.harvest_check_status,
        "version": b.version,
        "current_assignment": assignment_out(cur) if cur else None,
        "created_at": b.created_at,
    }
    if detail:
        d["assignments"] = [assignment_out(a) for a in b.assignments]
        d["harvest_check_details"] = b.harvest_check_details
    return d


def match_out(m: BuyerMatch) -> dict:
    return {
        "id": m.id,
        "buyer": {"id": m.buyer.id, "display_name": m.buyer.display_name, "buyer_type": m.buyer.buyer_type,
                  "district": m.buyer.district, "state": m.buyer.state, "delivery_preference": m.buyer.delivery_preference},
        "demand": {"id": m.demand.id, "accepted_grades": m.demand.accepted_grades, "quantity_kg": _f(m.demand.quantity_kg),
                   "delivery_start": m.demand.delivery_start, "delivery_end": m.demand.delivery_end,
                   "max_distance_km": m.demand.max_distance_km},
        "eligible": m.eligible,
        "score": m.score,
        "rank": m.rank,
        "distance_km": m.distance_km,
        "remaining_demand_kg": _f(m.remaining_demand_kg),
        "components": m.components,
        "reasons": m.reasons,
        "tradeoffs": m.tradeoffs,
        "exclusions": m.exclusions,
    }


def run_out(r: RerouteRun) -> dict:
    return {
        "id": r.id,
        "trigger": r.trigger,
        "note": r.note,
        "as_of_date": r.as_of_date,
        "scoring_version": r.scoring_version,
        "created_at": r.created_at,
        "matches": [match_out(m) for m in r.matches],
    }


def _my_batch(db: Session, user: User, batch_id: int) -> ProduceBatch:
    b = db.get(ProduceBatch, batch_id)
    if not b or (user.role == Role.FARMER and b.organization_id != user.organization_id) or user.role not in (Role.FARMER, Role.ADMIN):
        raise NotFound("Batch not found.")
    return b


# ---------------------------------------------------------------- batches (farmer)
class BatchIn(BaseModel):
    crop_cycle_id: int
    quantity_value: Decimal = PField(gt=0, le=Decimal("1000000"), decimal_places=2)
    unit: str = "kg"
    grade: str
    quality_notes: str | None = PField(default=None, max_length=1000)
    harvested_on: date
    shelf_life_days: int | None = PField(default=None, ge=1, le=365)
    storage_condition: str | None = PField(default=None, max_length=80)
    available_from: date | None = None
    deliver_by: date | None = None

    @field_validator("unit")
    @classmethod
    def _unit(cls, v):
        if v not in UNITS_TO_KG:
            raise ValueError("Unit must be kg, quintal or tonne.")
        return v

    @field_validator("grade")
    @classmethod
    def _grade(cls, v):
        if v not in GRADES:
            raise ValueError("Grade must be A, B or C.")
        return v

    @model_validator(mode="after")
    def _dates(self):
        af = self.available_from or self.harvested_on
        if af < self.harvested_on:
            raise ValueError("Available date cannot be before harvest.")
        if self.deliver_by and self.deliver_by < af:
            raise ValueError("Deliver-by date must be after the available date.")
        return self


@router.get("/batches")
def list_batches(
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(farmer_only),
):
    stmt = select(ProduceBatch).where(ProduceBatch.organization_id == user.organization_id).order_by(ProduceBatch.harvested_on.desc(), ProduceBatch.id.desc())
    if status == "active":
        stmt = stmt.where(ProduceBatch.status.notin_([BatchStatus.DELIVERED, BatchStatus.CLOSED]))
    elif status:
        stmt = stmt.where(ProduceBatch.status == status)
    return [batch_out(b) for b in db.scalars(stmt)]


@router.post("/batches", status_code=201)
def create_batch(body: BatchIn, db: Session = Depends(get_db), user: User = Depends(farmer_only)):
    cycle = get_cycle(db, user, body.crop_cycle_id, write=True)
    today = local_today(cycle.field.farm.timezone)
    if body.harvested_on > today:
        raise Unprocessable("Harvest date cannot be in the future.")
    if body.harvested_on < cycle.sowing_date:
        raise Unprocessable("Harvest date is before this cycle was sown.")
    check = evaluate_for_harvest_date(db, cycle, body.harvested_on)
    if check.earliest_eligible_date and check.earliest_eligible_date > body.harvested_on:
        raise Conflict(
            f"Harvest on {body.harvested_on:%d %b %Y} falls within a pre-harvest interval. "
            f"Earliest eligible date under recorded rules: {check.earliest_eligible_date:%d %b %Y}.",
            code="harvest_restricted",
            details={"earliest_eligible_date": str(check.earliest_eligible_date)},
        )
    harvest_status = "unknown" if check.unresolved_count else "eligible"
    qty_kg = (body.quantity_value * UNITS_TO_KG[body.unit]).quantize(Decimal("0.01"))
    seq = (db.scalar(select(func.count(ProduceBatch.id)).where(ProduceBatch.organization_id == user.organization_id)) or 0) + 1
    code = f"{cycle.crop.code[:3].upper()}-{body.harvested_on:%y%m%d}-{user.organization_id:02d}{seq:03d}"
    b = ProduceBatch(
        code=code,
        organization_id=user.organization_id,
        crop_cycle_id=cycle.id,
        crop_id=cycle.crop_id,
        quantity_value=body.quantity_value,
        unit=body.unit,
        quantity_kg=qty_kg,
        grade=body.grade,
        quality_notes=body.quality_notes,
        harvested_on=body.harvested_on,
        shelf_life_days=body.shelf_life_days,
        shelf_life_source="supplied" if body.shelf_life_days else None,
        storage_condition=body.storage_condition,
        available_from=body.available_from or body.harvested_on,
        deliver_by=body.deliver_by,
        status=BatchStatus.UNASSIGNED,
        harvest_check_status=harvest_status,
        harvest_check_details={"unresolved_count": check.unresolved_count, "rule_version": check.rule_version,
                               "uses_fictional_reference": check.uses_fictional_reference,
                               "earliest_eligible_date": str(check.earliest_eligible_date) if check.earliest_eligible_date else None},
        created_by=user.id,
    )
    db.add(b)
    db.flush()
    audit(db, actor_id=user.id, action="batch.created", entity_type="produce_batch", entity_id=b.id,
          after={"code": code, "quantity_kg": str(qty_kg), "grade": b.grade, "harvest_check": harvest_status})
    db.commit()
    db.refresh(b)
    return batch_out(b, detail=True)


@router.get("/batches/{batch_id}")
def get_batch(batch_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(Role.FARMER, Role.ADMIN))):
    b = _my_batch(db, user, batch_id)
    d = batch_out(b, detail=True)
    run = db.scalar(select(RerouteRun).where(RerouteRun.batch_id == b.id).order_by(RerouteRun.id.desc()).limit(1))
    d["latest_run"] = run_out(run) if run else None
    return d


class RerouteIn(BaseModel):
    trigger: RerouteTrigger
    note: str | None = PField(default=None, max_length=1000)


@router.post("/batches/{batch_id}/buyer-matches", status_code=201)
def request_matches(batch_id: int, body: RerouteIn, db: Session = Depends(get_db), user: User = Depends(farmer_only)):
    """Compute and store ranked alternative buyers for a batch."""
    b = _my_batch(db, user, batch_id)
    if body.trigger == RerouteTrigger.BUYER_CANCELLED and b.status != BatchStatus.NEEDS_DESTINATION:
        raise InvalidTransition("Use this after a buyer has cancelled.")
    run = start_reroute(db, user, b, body.trigger, body.note)
    db.commit()
    db.refresh(run)
    return run_out(run)


@router.get("/buyer-matches/{run_id}")
def get_matches(run_id: int, db: Session = Depends(get_db), user: User = Depends(farmer_only)):
    run = db.get(RerouteRun, run_id)
    if not run:
        raise NotFound("Not found.")
    _my_batch(db, user, run.batch_id)
    return run_out(run)


class ConfirmIn(BaseModel):
    match_id: int
    version: int


@router.post("/batches/{batch_id}/destination")
def confirm(
    batch_id: int,
    body: ConfirmIn,
    db: Session = Depends(get_db),
    user: User = Depends(farmer_only),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    def action():
        b = confirm_destination(db, user, batch_id, body.match_id, body.version)
        db.flush()
        db.refresh(b)
        return batch_out(b, detail=True)

    return run_idempotent(db, user_id=user.id, key=idempotency_key, scope=f"batch.destination:{batch_id}",
                          payload=body.model_dump(), action=action)


class WithdrawIn(BaseModel):
    reason: str = PField(min_length=3, max_length=500)


@router.post("/batches/{batch_id}/close")
def close_batch(batch_id: int, body: WithdrawIn, db: Session = Depends(get_db), user: User = Depends(farmer_only)):
    b = db.scalar(select(ProduceBatch).where(ProduceBatch.id == batch_id).with_for_update(of=ProduceBatch))
    if not b or b.organization_id != user.organization_id:
        raise NotFound("Batch not found.")
    if b.status in (BatchStatus.DELIVERED, BatchStatus.CLOSED, BatchStatus.IN_TRANSIT):
        raise InvalidTransition(f"A {b.status.replace('_', ' ')} batch cannot be closed.")
    cur = active_assignment(b)
    if cur:
        cur.status = AssignmentStatus.WITHDRAWN
        cur.ended_at = now_utc()
        cur.ended_by = user.id
        cur.end_reason = body.reason
        if cur.shipment and cur.shipment.status == ShipmentStatus.SCHEDULED:
            cur.shipment.status = ShipmentStatus.CANCELLED
    prev = b.status
    b.status = BatchStatus.CLOSED
    audit(db, actor_id=user.id, action="batch.closed", entity_type="produce_batch", entity_id=b.id,
          before={"status": prev}, after={"status": "closed", "reason": body.reason})
    db.commit()
    db.refresh(b)
    return batch_out(b, detail=True)


class ShipmentAdvance(BaseModel):
    to: ShipmentStatus
    note: str | None = PField(default=None, max_length=500)


@router.post("/shipments/{shipment_id}/status")
def shipment_status(shipment_id: int, body: ShipmentAdvance, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.FARMER, Role.BUYER))):
    sh = advance_shipment(db, user, shipment_id, body.to.value, body.note)
    db.commit()
    db.refresh(sh)
    return shipment_out(sh)


# ---------------------------------------------------------------- buyers
def buyer_out(b: BuyerProfile) -> dict:
    return {
        "id": b.id,
        "display_name": b.display_name,
        "buyer_type": b.buyer_type,
        "district": b.district,
        "state": b.state,
        "has_location": b.latitude is not None,
        "receiving_capacity_kg_per_day": _f(b.receiving_capacity_kg_per_day),
        "delivery_preference": b.delivery_preference,
        "contact_phone": b.contact_phone,
        "is_active": b.is_active,
    }


def demand_out(db: Session, d: BuyerDemand) -> dict:
    alloc = allocated_kg(db, d.id)
    return {
        "id": d.id,
        "crop": {"id": d.crop.id, "name": d.crop.name},
        "accepted_grades": d.accepted_grades,
        "quantity_kg": _f(d.quantity_kg),
        "allocated_kg": _f(alloc),
        "remaining_kg": _f(max(Decimal(d.quantity_kg) - alloc, Decimal(0))),
        "valid_from": d.valid_from,
        "valid_until": d.valid_until,
        "delivery_start": d.delivery_start,
        "delivery_end": d.delivery_end,
        "max_distance_km": d.max_distance_km,
        "status": d.status,
        "notes": d.notes,
    }


def _my_buyer(db: Session, user: User) -> BuyerProfile:
    b = db.scalar(select(BuyerProfile).where(BuyerProfile.organization_id == user.organization_id))
    if not b:
        raise NotFound("No buyer profile for this account.")
    return b


@router.get("/buyers")
def list_buyers(db: Session = Depends(get_db), _: User = Depends(require_roles(Role.FARMER, Role.ADMIN))):
    return [buyer_out(b) for b in db.scalars(select(BuyerProfile).where(BuyerProfile.is_active.is_(True)).order_by(BuyerProfile.display_name))]


@router.get("/buyers/me")
def my_buyer(db: Session = Depends(get_db), user: User = Depends(buyer_only)):
    return buyer_out(_my_buyer(db, user))


class BuyerProfileIn(BaseModel):
    display_name: str = PField(min_length=2, max_length=160)
    buyer_type: str = PField(min_length=2, max_length=60)
    receiving_capacity_kg_per_day: Decimal | None = PField(default=None, gt=0)
    delivery_preference: str = "either"
    contact_phone: str | None = PField(default=None, max_length=32)

    @field_validator("delivery_preference")
    @classmethod
    def _pref(cls, v):
        if v not in ("buyer_pickup", "farm_delivery", "either"):
            raise ValueError("Unknown delivery preference.")
        return v


@router.put("/buyers/me")
def update_my_buyer(body: BuyerProfileIn, db: Session = Depends(get_db), user: User = Depends(buyer_only)):
    b = _my_buyer(db, user)
    for k, v in body.model_dump().items():
        setattr(b, k, v)
    audit(db, actor_id=user.id, action="buyer.profile_updated", entity_type="buyer", entity_id=b.id)
    db.commit()
    return buyer_out(b)


class DemandIn(BaseModel):
    crop_id: int
    accepted_grades: list[str] = PField(min_length=1)
    quantity_kg: Decimal = PField(gt=0, le=Decimal("10000000"))
    valid_from: date
    valid_until: date
    delivery_start: date
    delivery_end: date
    max_distance_km: float | None = PField(default=None, gt=0, le=3000)
    notes: str | None = PField(default=None, max_length=1000)

    @field_validator("accepted_grades")
    @classmethod
    def _grades(cls, v):
        bad = [g for g in v if g not in GRADES]
        if bad:
            raise ValueError("Grades must be A, B or C.")
        return sorted(set(v))

    @model_validator(mode="after")
    def _dates(self):
        if self.valid_until < self.valid_from:
            raise ValueError("Valid-until must be after valid-from.")
        if self.delivery_end < self.delivery_start:
            raise ValueError("Delivery end must be after delivery start.")
        return self


@router.get("/buyer-demands")
def list_demands(db: Session = Depends(get_db), user: User = Depends(buyer_only)):
    b = _my_buyer(db, user)
    return [demand_out(db, d) for d in db.scalars(select(BuyerDemand).where(BuyerDemand.buyer_id == b.id).order_by(BuyerDemand.valid_until.desc()))]


@router.post("/buyer-demands", status_code=201)
def create_demand(body: DemandIn, db: Session = Depends(get_db), user: User = Depends(buyer_only)):
    b = _my_buyer(db, user)
    if not db.get(CropReference, body.crop_id):
        raise Unprocessable("Unknown crop.")
    if body.valid_until < local_today(get_settings().default_timezone):
        raise Unprocessable("Demand must be valid on a future date.")
    d = BuyerDemand(buyer_id=b.id, **body.model_dump(), status=DemandStatus.OPEN, created_by=user.id)
    db.add(d)
    db.flush()
    audit(db, actor_id=user.id, action="demand.created", entity_type="buyer_demand", entity_id=d.id,
          after={"crop_id": d.crop_id, "quantity_kg": str(d.quantity_kg)})
    db.commit()
    db.refresh(d)
    return demand_out(db, d)


class DemandStatusIn(BaseModel):
    status: DemandStatus


@router.post("/buyer-demands/{demand_id}/status")
def set_demand_status(demand_id: int, body: DemandStatusIn, db: Session = Depends(get_db), user: User = Depends(buyer_only)):
    b = _my_buyer(db, user)
    d = db.get(BuyerDemand, demand_id)
    if not d or d.buyer_id != b.id:
        raise NotFound("Demand not found.")
    if d.status == DemandStatus.CLOSED:
        raise InvalidTransition("Closed demand cannot be reopened; create a new listing.")
    prev = d.status
    d.status = body.status
    audit(db, actor_id=user.id, action="demand.status_changed", entity_type="buyer_demand", entity_id=d.id,
          before={"status": prev}, after={"status": d.status})
    db.commit()
    return demand_out(db, d)


@router.get("/buyers/me/deliveries")
def my_deliveries(db: Session = Depends(get_db), user: User = Depends(buyer_only)):
    b = _my_buyer(db, user)
    rows = db.scalars(select(BatchAssignment).where(BatchAssignment.buyer_id == b.id).order_by(BatchAssignment.assigned_at.desc())).all()
    out = []
    for a in rows:
        batch = a.batch
        out.append({
            **assignment_out(a),
            "batch": {
                "id": batch.id, "code": batch.code, "crop": batch.crop.name, "grade": batch.grade,
                "quantity_kg": _f(batch.quantity_kg), "harvested_on": batch.harvested_on,
                "source_district": batch.crop_cycle.field.farm.district if batch.crop_cycle else None,
                "status": batch.status,
            },
        })
    return out


class CancelIn(BaseModel):
    reason: str = PField(min_length=3, max_length=500)


@router.post("/buyers/me/deliveries/{assignment_id}/cancel")
def cancel_delivery(assignment_id: int, body: CancelIn, db: Session = Depends(get_db), user: User = Depends(buyer_only)):
    a = buyer_cancel(db, user, assignment_id, body.reason)
    db.commit()
    db.refresh(a)
    return assignment_out(a)


@router.get("/buyers/me/matching-produce")
def matching_produce(db: Session = Depends(get_db), user: User = Depends(buyer_only)):
    """Batches currently looking for a destination that satisfy one of this buyer's open demands.
    Only crop, quantity, grade and dates are shown — not the farm's identity."""
    b = _my_buyer(db, user)
    demands = db.scalars(select(BuyerDemand).where(BuyerDemand.buyer_id == b.id, BuyerDemand.status == DemandStatus.OPEN)).all()
    if not demands:
        return []
    from app.modules.produce.service import demand_view

    views = [demand_view(db, d) for d in demands]
    batches = db.scalars(
        select(ProduceBatch).where(
            ProduceBatch.status.in_([BatchStatus.UNASSIGNED, BatchStatus.NEEDS_DESTINATION]),
            ProduceBatch.crop_id.in_({d.crop_id for d in demands}),
        )
    ).all()
    out = []
    for batch in batches:
        today = local_today(batch_tz(batch))
        cands = [c for c in ranking.rank(batch_view(batch), views, today) if c.eligible]
        if cands:
            out.append({
                "batch_code": batch.code,
                "crop": batch.crop.name,
                "grade": batch.grade,
                "quantity_kg": _f(batch.quantity_kg),
                "harvested_on": batch.harvested_on,
                "sell_by": ranking.sell_by(batch_view(batch)),
                "district": batch.crop_cycle.field.farm.district if batch.crop_cycle else None,
                "distance_km": cands[0].distance_km,
                "demand_id": cands[0].demand.demand_id,
            })
    return out
