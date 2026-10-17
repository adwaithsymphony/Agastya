from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field as PField, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import local_today
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import current_user, farmer_only, provider_only, require_roles
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.core.events import audit, notify, org_user_ids
from app.core.idempotency import run_idempotent
from app.modules.farms.models import CropCycle, CropReference, CycleStatus
from app.modules.farms.router import cycle_brief
from app.modules.farms.service import farmer_cycles_stmt, get_cycle
from app.modules.identity.models import Role, User
from app.modules.pollination.models import (
    BookingEvent,
    BookingStatus,
    PollinationBooking,
    ProviderAvailability,
    ProviderCrop,
    ProviderProfile,
    ProviderServiceArea,
)
from app.modules.pollination.service import (
    capacity_profile,
    check_transition,
    ensure_capacity,
    ensure_no_overlap_for_cycle,
    match_providers,
    remaining_capacity,
    validate_window,
)

router = APIRouter(prefix="/pollination", tags=["pollination"])


def provider_out(p: ProviderProfile, db: Session | None = None, detail: bool = False) -> dict:
    d = {
        "id": p.id,
        "display_name": p.display_name,
        "provider_type": p.provider_type,
        "pollinator": p.pollinator,
        "base_district": p.base_district,
        "base_state": p.base_state,
        "service_radius_km": p.service_radius_km,
        "colonies_total": p.colonies_total,
        "is_active": p.is_active,
        "crops": [{"id": c.crop.id, "name": c.crop.name} for c in p.crops],
        "service_areas": [{"id": a.id, "district": a.district, "state": a.state} for a in p.service_areas],
        "has_location": p.latitude is not None,
    }
    if detail:
        d["description"] = p.description
        d["contact_phone"] = p.contact_phone
        d["latitude"] = p.latitude
        d["longitude"] = p.longitude
        if db is not None:
            d["availability"] = [
                {
                    "id": w.id,
                    "start_date": w.start_date,
                    "end_date": w.end_date,
                    "colonies_available": w.colonies_available,
                    "min_free": remaining_capacity(db, p, w.start_date, w.end_date),
                    "notes": w.notes,
                }
                for w in p.availability
            ]
    return d


def booking_out(b: PollinationBooking, include_events: bool = False) -> dict:
    c = b.crop_cycle
    d = {
        "id": b.id,
        "status": b.status,
        "start_date": b.start_date,
        "end_date": b.end_date,
        "colonies_requested": b.colonies_requested,
        "proposed_start_date": b.proposed_start_date,
        "proposed_end_date": b.proposed_end_date,
        "farmer_note": b.farmer_note,
        "provider_note": b.provider_note,
        "version": b.version,
        "created_at": b.created_at,
        "updated_at": b.updated_at,
        "provider": {"id": b.provider.id, "display_name": b.provider.display_name, "contact_phone": b.provider.contact_phone},
        "cycle": {
            "id": c.id,
            "crop": c.crop.name,
            "field": c.field.name,
            "area_ha": c.field.area_ha,
            "farm": c.field.farm.name,
            "district": c.field.farm.district,
            "state": c.field.farm.state,
            "village": c.field.farm.village,
            "flowering_start": c.expected_flowering_start,
            "flowering_end": c.expected_flowering_end,
        },
    }
    if include_events:
        d["events"] = [
            {"from": e.from_status, "to": e.to_status, "note": e.note, "actor": e.actor.full_name if e.actor else None, "at": e.created_at}
            for e in b.events
        ]
    return d


def _my_provider(db: Session, user: User) -> ProviderProfile:
    p = db.scalar(select(ProviderProfile).where(ProviderProfile.organization_id == user.organization_id))
    if not p:
        raise NotFound("No provider profile for this account.")
    return p


def _get_booking(db: Session, user: User, booking_id: int) -> PollinationBooking:
    b = db.get(PollinationBooking, booking_id)
    if not b:
        raise NotFound("Booking not found.")
    if user.role == Role.FARMER:
        get_cycle(db, user, b.crop_cycle_id)  # raises NotFound if not owner
    elif user.role == Role.PROVIDER:
        if b.provider.organization_id != user.organization_id:
            raise NotFound("Booking not found.")
    elif user.role != Role.ADMIN:
        raise NotFound("Booking not found.")
    return b


# ---------------------------------------------------------------- farmer views
@router.get("/calendar")
def flowering_calendar(db: Session = Depends(get_db), user: User = Depends(farmer_only)):
    cycles = db.scalars(farmer_cycles_stmt(user).where(CropCycle.status != CycleStatus.CLOSED).order_by(CropCycle.expected_flowering_start.asc().nulls_last())).all()
    ids = [c.id for c in cycles]
    bookings = db.scalars(select(PollinationBooking).where(PollinationBooking.crop_cycle_id.in_(ids)).order_by(PollinationBooking.start_date)).all() if ids else []
    return {
        "cycles": [{**cycle_brief(c), "pollinator_dependent": c.crop.pollinator_dependent} for c in cycles],
        "bookings": [booking_out(b) for b in bookings],
    }


@router.get("/providers")
def list_providers(crop_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    stmt = select(ProviderProfile).where(ProviderProfile.is_active.is_(True)).order_by(ProviderProfile.display_name)
    if crop_id:
        stmt = stmt.join(ProviderCrop, ProviderCrop.provider_id == ProviderProfile.id).where(ProviderCrop.crop_id == crop_id)
    return [provider_out(p) for p in db.scalars(stmt)]


@router.get("/providers/match")
def match(
    crop_cycle_id: int,
    start_date: date,
    end_date: date,
    colonies: int | None = Query(None, ge=1, le=10000),
    db: Session = Depends(get_db),
    user: User = Depends(farmer_only),
):
    cycle = get_cycle(db, user, crop_cycle_id)
    if end_date < start_date:
        raise Unprocessable("End date must be on or after start date.")
    if (end_date - start_date).days > 60:
        raise Unprocessable("Search windows are limited to 60 days.")
    results = match_providers(db, cycle, start_date, end_date, colonies)
    return [
        {
            "provider": provider_out(m.provider),
            "eligible": m.eligible,
            "score": m.score,
            "distance_km": m.distance_km,
            "free_colonies": m.free_colonies,
            "covered_days": m.overlap_days,
            "window_days": m.window_days,
            "reasons": m.reasons,
            "exclusions": m.exclusions,
        }
        for m in results
    ]


@router.get("/providers/{provider_id}")
def provider_detail(provider_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    p = db.get(ProviderProfile, provider_id)
    if not p or not p.is_active:
        raise NotFound("Provider not found.")
    return provider_out(p, db, detail=True)


class BookingIn(BaseModel):
    crop_cycle_id: int
    provider_id: int
    start_date: date
    end_date: date
    colonies_requested: int = PField(ge=1, le=10000)
    farmer_note: str | None = PField(default=None, max_length=1000)


@router.post("/bookings", status_code=201)
def create_booking(
    body: BookingIn,
    db: Session = Depends(get_db),
    user: User = Depends(farmer_only),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    def action():
        cycle = get_cycle(db, user, body.crop_cycle_id, write=True)
        if cycle.status == CycleStatus.CLOSED:
            raise Conflict("This crop cycle is closed.")
        provider = db.get(ProviderProfile, body.provider_id)
        if not provider or not provider.is_active:
            raise NotFound("Provider not found.")
        today = local_today(cycle.field.farm.timezone)
        validate_window(cycle, body.start_date, body.end_date, today)
        matches = {m.provider.id: m for m in match_providers(db, cycle, body.start_date, body.end_date, body.colonies_requested)}
        m = matches.get(provider.id)
        if not m or not m.eligible:
            raise Conflict("This provider cannot take this request: " + "; ".join(m.exclusions if m else ["not found"]), code="provider_incompatible")
        ensure_no_overlap_for_cycle(db, cycle.id, body.start_date, body.end_date)
        b = PollinationBooking(**body.model_dump(), requested_by=user.id, status=BookingStatus.REQUESTED)
        db.add(b)
        db.flush()
        db.add(BookingEvent(booking_id=b.id, from_status=None, to_status=BookingStatus.REQUESTED, actor_id=user.id, note=body.farmer_note))
        audit(db, actor_id=user.id, action="booking.requested", entity_type="pollination_booking", entity_id=b.id,
              after={"provider": provider.display_name, "window": [str(b.start_date), str(b.end_date)], "colonies": b.colonies_requested})
        notify(db, org_user_ids(db, provider.organization_id, Role.PROVIDER), event_type="booking.requested",
               title=f"New request: {cycle.crop.name}, {cycle.field.farm.district}",
               body=f"{b.colonies_requested} colonies, {b.start_date:%d %b} – {b.end_date:%d %b}.",
               entity_type="pollination_booking", entity_id=b.id, link=f"/app/provider/bookings?id={b.id}")
        db.flush()
        db.refresh(b)
        return booking_out(b)

    return run_idempotent(db, user_id=user.id, key=idempotency_key, scope="booking.create", payload=body.model_dump(), action=action)


@router.get("/bookings")
def list_bookings(
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER, Role.PROVIDER, Role.ADMIN)),
):
    stmt = select(PollinationBooking).order_by(PollinationBooking.start_date.desc())
    if user.role == Role.FARMER:
        stmt = stmt.where(PollinationBooking.crop_cycle_id.in_(farmer_cycles_stmt(user).with_only_columns(CropCycle.id)))
    elif user.role == Role.PROVIDER:
        stmt = stmt.where(PollinationBooking.provider_id == _my_provider(db, user).id)
    if status == "open":
        stmt = stmt.where(PollinationBooking.status.in_([BookingStatus.REQUESTED, BookingStatus.ACCEPTED, BookingStatus.RESCHEDULE_PROPOSED]))
    elif status:
        stmt = stmt.where(PollinationBooking.status == status)
    return [booking_out(b) for b in db.scalars(stmt)]


@router.get("/bookings/{booking_id}")
def get_booking(booking_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return booking_out(_get_booking(db, user, booking_id), include_events=True)


class TransitionIn(BaseModel):
    to: BookingStatus
    version: int
    start_date: date | None = None
    end_date: date | None = None
    note: str | None = PField(default=None, max_length=1000)

    @model_validator(mode="after")
    def _dates(self):
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("Provide both start and end dates.")
        return self


@router.post("/bookings/{booking_id}/transition")
def transition_booking(
    booking_id: int,
    body: TransitionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER, Role.PROVIDER)),
):
    b = _get_booking(db, user, booking_id)
    if b.version != body.version:
        raise Conflict("This booking was updated by someone else. Reload and try again.", code="stale_version")
    to = body.to.value
    check_transition(b, to, user.role)
    cycle = b.crop_cycle
    tz = cycle.field.farm.timezone
    today = local_today(tz)
    # Serialise capacity-affecting changes per provider.
    provider = db.scalar(select(ProviderProfile).where(ProviderProfile.id == b.provider_id).with_for_update(of=ProviderProfile))
    frm = b.status

    if to == BookingStatus.ACCEPTED:
        if frm == BookingStatus.RESCHEDULE_PROPOSED:
            b.start_date, b.end_date = b.proposed_start_date, b.proposed_end_date
            b.proposed_start_date = b.proposed_end_date = None
        if b.start_date < today:
            raise Conflict("The booking window has already started; propose new dates instead.")
        ensure_capacity(db, provider, b.start_date, b.end_date, b.colonies_requested, exclude_booking_id=b.id)
        ensure_no_overlap_for_cycle(db, cycle.id, b.start_date, b.end_date, exclude_booking_id=b.id)
    elif to == BookingStatus.RESCHEDULE_PROPOSED:
        if not body.start_date:
            raise Unprocessable("Propose new start and end dates.")
        validate_window(cycle, body.start_date, body.end_date, today)
        ensure_capacity(db, provider, body.start_date, body.end_date, b.colonies_requested, exclude_booking_id=b.id)
        b.proposed_start_date, b.proposed_end_date = body.start_date, body.end_date
    elif to == BookingStatus.REQUESTED:
        if not body.start_date:
            raise Unprocessable("Choose new start and end dates.")
        validate_window(cycle, body.start_date, body.end_date, today)
        ensure_no_overlap_for_cycle(db, cycle.id, body.start_date, body.end_date, exclude_booking_id=b.id)
        b.start_date, b.end_date = body.start_date, body.end_date
        b.proposed_start_date = b.proposed_end_date = None
    elif to == BookingStatus.COMPLETED:
        if today < b.start_date:
            raise Conflict("A booking can only be completed once its service window has started.")
    elif to == BookingStatus.CANCELLED and frm == BookingStatus.ACCEPTED and user.role == Role.PROVIDER and today >= b.start_date:
        raise Conflict("The service window has started; contact the farmer to resolve this booking.")

    if user.role == Role.PROVIDER and body.note:
        b.provider_note = body.note
    if user.role == Role.FARMER and body.note:
        b.farmer_note = body.note
    b.status = to
    db.add(BookingEvent(booking_id=b.id, from_status=frm, to_status=to, actor_id=user.id, note=body.note))
    audit(db, actor_id=user.id, action=f"booking.{to}", entity_type="pollination_booking", entity_id=b.id,
          before={"status": frm}, after={"status": to, "window": [str(b.start_date), str(b.end_date)]})

    titles = {
        BookingStatus.ACCEPTED: "Pollination booking accepted",
        BookingStatus.REJECTED: "Pollination request declined",
        BookingStatus.RESCHEDULE_PROPOSED: "Provider proposed new dates",
        BookingStatus.CANCELLED: "Pollination booking cancelled",
        BookingStatus.COMPLETED: "Pollination service marked complete",
        BookingStatus.REQUESTED: "Booking dates changed — please confirm",
    }
    if user.role == Role.PROVIDER:
        recipients = org_user_ids(db, cycle.field.farm.organization_id, Role.FARMER)
        link = "/app/pollination"
    else:
        recipients = org_user_ids(db, provider.organization_id, Role.PROVIDER)
        link = f"/app/provider/bookings?id={b.id}"
    notify(db, recipients, event_type=f"booking.{to}", title=titles[BookingStatus(to)],
           body=f"{cycle.crop.name}, {cycle.field.farm.name}: {b.start_date:%d %b} – {b.end_date:%d %b}.",
           entity_type="pollination_booking", entity_id=b.id, link=link,
           severity="warning" if to in (BookingStatus.REJECTED, BookingStatus.CANCELLED) else "info")
    db.commit()
    db.refresh(b)
    return booking_out(b, include_events=True)


# ---------------------------------------------------------------- provider workspace
@router.get("/profile")
def my_profile(db: Session = Depends(get_db), user: User = Depends(provider_only)):
    return provider_out(_my_provider(db, user), db, detail=True)


class AreaIn(BaseModel):
    district: str = PField(min_length=2, max_length=80)
    state: str = PField(min_length=2, max_length=80)


class ProfileIn(BaseModel):
    display_name: str = PField(min_length=2, max_length=160)
    description: str | None = PField(default=None, max_length=2000)
    contact_phone: str | None = PField(default=None, max_length=32)
    service_radius_km: float | None = PField(default=None, gt=0, le=2000)
    colonies_total: int = PField(ge=0, le=100000)
    is_active: bool = True
    crop_ids: list[int] = PField(default_factory=list, max_length=60)
    service_areas: list[AreaIn] = PField(default_factory=list, max_length=60)


@router.put("/profile")
def update_profile(body: ProfileIn, db: Session = Depends(get_db), user: User = Depends(provider_only)):
    p = _my_provider(db, user)
    known = set(db.scalars(select(CropReference.id).where(CropReference.id.in_(body.crop_ids))))
    if known != set(body.crop_ids):
        raise Unprocessable("Unknown crop in list.")
    over = [w for w in p.availability if w.colonies_available > body.colonies_total]
    if over:
        raise Conflict("Some availability windows offer more colonies than the new total.")
    p.display_name = body.display_name
    p.description = body.description
    p.contact_phone = body.contact_phone
    p.service_radius_km = body.service_radius_km
    p.colonies_total = body.colonies_total
    p.is_active = body.is_active
    p.crops = [ProviderCrop(provider_id=p.id, crop_id=cid) for cid in sorted(set(body.crop_ids))]
    seen = {}
    for a in body.service_areas:
        seen[(a.district.strip().lower(), a.state.strip().lower())] = a
    p.service_areas = [ProviderServiceArea(provider_id=p.id, district=a.district.strip(), state=a.state.strip()) for a in seen.values()]
    audit(db, actor_id=user.id, action="provider.profile_updated", entity_type="provider", entity_id=p.id)
    db.commit()
    db.refresh(p)
    return provider_out(p, db, detail=True)


class AvailabilityIn(BaseModel):
    start_date: date
    end_date: date
    colonies_available: int = PField(ge=1, le=100000)
    notes: str | None = PField(default=None, max_length=255)

    @model_validator(mode="after")
    def _order(self):
        if self.end_date < self.start_date:
            raise ValueError("End date must be on or after start date.")
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("Availability windows are limited to one year.")
        return self


@router.post("/availability", status_code=201)
def add_availability(body: AvailabilityIn, db: Session = Depends(get_db), user: User = Depends(provider_only)):
    p = db.scalar(select(ProviderProfile).where(ProviderProfile.organization_id == user.organization_id).with_for_update(of=ProviderProfile))
    if not p:
        raise NotFound("No provider profile for this account.")
    if body.colonies_available > p.colonies_total:
        raise Unprocessable("Availability cannot exceed your total colonies.")
    if body.end_date < local_today(get_settings().default_timezone):
        raise Unprocessable("Availability must include future dates.")
    overlap = db.scalar(
        select(ProviderAvailability).where(
            ProviderAvailability.provider_id == p.id,
            ProviderAvailability.start_date <= body.end_date,
            ProviderAvailability.end_date >= body.start_date,
        )
    )
    if overlap:
        raise Conflict(f"Overlaps an existing window ({overlap.start_date:%d %b} – {overlap.end_date:%d %b}).")
    w = ProviderAvailability(provider_id=p.id, **body.model_dump())
    db.add(w)
    audit(db, actor_id=user.id, action="provider.availability_added", entity_type="provider", entity_id=p.id,
          after={"window": [str(w.start_date), str(w.end_date)], "colonies": w.colonies_available})
    db.commit()
    db.refresh(p)
    return provider_out(p, db, detail=True)


@router.delete("/availability/{window_id}")
def delete_availability(window_id: int, db: Session = Depends(get_db), user: User = Depends(provider_only)):
    p = db.scalar(select(ProviderProfile).where(ProviderProfile.organization_id == user.organization_id).with_for_update(of=ProviderProfile))
    w = db.get(ProviderAvailability, window_id)
    if not p or not w or w.provider_id != p.id:
        raise NotFound("Availability window not found.")
    committed = db.scalar(
        select(PollinationBooking).where(
            PollinationBooking.provider_id == p.id,
            PollinationBooking.status == BookingStatus.ACCEPTED,
            PollinationBooking.start_date <= w.end_date,
            PollinationBooking.end_date >= w.start_date,
        )
    )
    if committed:
        raise Conflict("Accepted bookings depend on this window. Cancel or complete them first.")
    db.delete(w)
    audit(db, actor_id=user.id, action="provider.availability_removed", entity_type="provider", entity_id=p.id,
          before={"window": [str(w.start_date), str(w.end_date)]})
    db.commit()
    db.refresh(p)
    return provider_out(p, db, detail=True)


@router.get("/capacity")
def capacity(
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db),
    user: User = Depends(provider_only),
):
    if end_date < start_date or (end_date - start_date).days > 120:
        raise Unprocessable("Choose a range of up to 120 days.")
    p = _my_provider(db, user)
    prof = capacity_profile(db, p, start_date, end_date)
    return [{"date": d, "available": a, "committed": c} for d, (a, c) in prof.items()]
