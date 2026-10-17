"""Role-aware dashboard. Every figure is derived from stored records at request time."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import local_today
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import current_user
from app.modules.audit.models import AuditEvent
from app.modules.farms.models import CropCycle, CycleStatus, Farm, Field
from app.modules.farms.router import cycle_brief
from app.modules.farms.service import farmer_cycles_stmt
from app.modules.identity.models import Role, User
from app.modules.monitoring.models import CropObservation, HumanReview, PredictionStatus, ReviewStatus
from app.modules.monitoring.router import _cycle_ctx, observation_brief
from app.modules.notifications.models import Notification
from app.modules.pesticide.models import LabelVerification, ProductLabel
from app.modules.pesticide.service import evaluate_cycle
from app.modules.pollination.models import BookingStatus, PollinationBooking, ProviderProfile
from app.modules.pollination.router import booking_out
from app.modules.pollination.service import capacity_profile
from app.modules.produce.models import (
    AssignmentStatus,
    BatchAssignment,
    BatchStatus,
    BuyerDemand,
    BuyerProfile,
    DemandStatus,
    ProduceBatch,
)
from app.modules.produce.router import batch_out, demand_out, matching_produce, my_deliveries

router = APIRouter(tags=["dashboard"])


def _recent(db: Session, user: User, n: int = 6) -> list[dict]:
    rows = db.scalars(
        select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(n)
    ).all()
    return [{"id": r.id, "title": r.title, "body": r.body, "link": r.link, "created_at": r.created_at, "severity": r.severity,
             "read": r.read_at is not None} for r in rows]


def farmer_dashboard(db: Session, user: User) -> dict:
    tz = get_settings().default_timezone
    today = local_today(tz)
    cycles = db.scalars(farmer_cycles_stmt(user).where(CropCycle.status != CycleStatus.CLOSED).order_by(CropCycle.sowing_date)).all()
    attention: list[dict] = []
    harvest = []
    for c in cycles:
        a = evaluate_cycle(db, c)
        harvest.append({"cycle": cycle_brief(c), "status": a.status, "earliest_eligible_date": a.earliest_eligible_date,
                        "days_until_eligible": a.days_until_eligible, "unresolved_count": a.unresolved_count})
        if a.status == "unknown" or a.unresolved_count:
            attention.append({"kind": "harvest_unknown", "title": f"{c.crop.name} · {c.field.name}: pesticide record needs verified label data",
                              "link": f"/app/harvest?cycle={c.id}", "severity": "warning"})
    ids = [c.id for c in cycles]
    bookings = db.scalars(
        select(PollinationBooking).where(
            PollinationBooking.crop_cycle_id.in_(ids) if ids else False,
            PollinationBooking.status.in_([BookingStatus.REQUESTED, BookingStatus.ACCEPTED, BookingStatus.RESCHEDULE_PROPOSED]),
        ).order_by(PollinationBooking.start_date)
    ).all() if ids else []
    for b in bookings:
        if b.status == BookingStatus.RESCHEDULE_PROPOSED:
            attention.append({"kind": "booking_reschedule", "title": f"{b.provider.display_name} proposed new dates for {b.crop_cycle.crop.name}",
                              "link": "/app/pollination", "severity": "info"})
    booked_cycles = {b.crop_cycle_id for b in bookings}
    flowering = []
    for c in cycles:
        if c.expected_flowering_start and c.expected_flowering_end and c.expected_flowering_end >= today and c.expected_flowering_start <= today + timedelta(days=60):
            flowering.append({**cycle_brief(c), "has_open_booking": c.id in booked_cycles, "pollinator_dependent": c.crop.pollinator_dependent,
                              "days_to_flowering": (c.expected_flowering_start - today).days})
            if c.crop.pollinator_dependent and c.id not in booked_cycles and (c.expected_flowering_start - today).days <= 30:
                attention.append({"kind": "flowering_unbooked", "title": f"{c.crop.name} · {c.field.name} flowers {c.expected_flowering_start:%d %b}; no pollination booked",
                                  "link": "/app/pollination", "severity": "info"})
    batches = db.scalars(
        select(ProduceBatch).where(ProduceBatch.organization_id == user.organization_id,
                                   ProduceBatch.status.notin_([BatchStatus.DELIVERED, BatchStatus.CLOSED]))
        .order_by(ProduceBatch.harvested_on.desc())
    ).all()
    for b in batches:
        if b.status in (BatchStatus.NEEDS_DESTINATION, BatchStatus.UNASSIGNED):
            attention.insert(0, {"kind": "batch_destination", "title": f"{b.code}: {b.quantity_kg:,.0f} kg {b.crop.name} needs a buyer",
                                 "link": f"/app/batches/{b.id}", "severity": "critical" if b.status == BatchStatus.NEEDS_DESTINATION else "warning"})
    obs = db.scalars(
        select(CropObservation).where(CropObservation.crop_cycle_id.in_(ids) if ids else False)
        .order_by(CropObservation.observed_at.desc()).limit(5)
    ).all() if ids else []
    for o in obs:
        if o.status in (PredictionStatus.UNCERTAIN, PredictionStatus.FAILED, PredictionStatus.UNSUPPORTED_INPUT) and o.review_status != ReviewStatus.REVIEWED:
            attention.append({"kind": "observation", "title": f"Observation #{o.id}: result {o.status.replace('_', ' ')} — awaiting review",
                              "link": f"/app/observations/{o.id}", "severity": "info"})

    rerouted = db.execute(
        select(BatchAssignment.status, func.coalesce(func.sum(BatchAssignment.quantity_kg), 0))
        .join(ProduceBatch, ProduceBatch.id == BatchAssignment.batch_id)
        .where(ProduceBatch.organization_id == user.organization_id,
               BatchAssignment.reason.in_(["reroute_buyer_cancelled", "reroute_disruption"]),
               BatchAssignment.status.in_([AssignmentStatus.ACTIVE, AssignmentStatus.COMPLETED]))
        .group_by(BatchAssignment.status)
    ).all()
    rr = {s: float(v) for s, v in rerouted}
    harvest_order = {"restricted": 0, "upcoming": 1, "unknown": 2, "eligible": 3}
    harvest.sort(key=lambda h: harvest_order[h["status"]])
    return {
        "role": "farmer",
        "today": today,
        "metrics": {
            "active_cycles": len(cycles),
            "fields": db.scalar(select(func.count(Field.id)).join(Farm).where(Farm.organization_id == user.organization_id)),
            "harvest_restricted": sum(1 for h in harvest if h["status"] in ("restricted", "upcoming")),
            "harvest_unknown": sum(1 for h in harvest if h["status"] == "unknown" or h["unresolved_count"]),
            "open_bookings": len(bookings),
            "batches_needing_destination": sum(1 for b in batches if b.status in (BatchStatus.NEEDS_DESTINATION, BatchStatus.UNASSIGNED)),
            "rerouted_delivered_kg": rr.get(AssignmentStatus.COMPLETED.value, 0.0),
            "rerouted_pending_kg": rr.get(AssignmentStatus.ACTIVE.value, 0.0),
        },
        "attention": attention[:8],
        "cycles": [cycle_brief(c) for c in cycles],
        "harvest": harvest,
        "flowering": sorted(flowering, key=lambda f: f["expected_flowering_start"]),
        "bookings": [booking_out(b) for b in bookings],
        "batches": [batch_out(b) for b in batches],
        "recent_observations": [{**observation_brief(o), "cycle": _cycle_ctx(db.get(CropCycle, o.crop_cycle_id))} for o in obs],
        "recent": _recent(db, user),
    }


def provider_dashboard(db: Session, user: User) -> dict:
    p = db.scalar(select(ProviderProfile).where(ProviderProfile.organization_id == user.organization_id))
    if not p:
        return {"role": "provider", "profile_missing": True}
    today = local_today(get_settings().default_timezone)
    reqs = db.scalars(select(PollinationBooking).where(PollinationBooking.provider_id == p.id,
                                                       PollinationBooking.status == BookingStatus.REQUESTED).order_by(PollinationBooking.start_date)).all()
    upcoming = db.scalars(select(PollinationBooking).where(PollinationBooking.provider_id == p.id,
                                                           PollinationBooking.status == BookingStatus.ACCEPTED,
                                                           PollinationBooking.end_date >= today).order_by(PollinationBooking.start_date)).all()
    waiting = db.scalars(select(PollinationBooking).where(PollinationBooking.provider_id == p.id,
                                                          PollinationBooking.status == BookingStatus.RESCHEDULE_PROPOSED)).all()
    prof = capacity_profile(db, p, today, today + timedelta(days=59))
    weekly = []
    days = sorted(prof)
    for i in range(0, len(days), 7):
        chunk = days[i:i + 7]
        weekly.append({"week_start": chunk[0], "available": min(prof[d][0] for d in chunk), "committed": max(prof[d][1] for d in chunk)})
    return {
        "role": "provider",
        "today": today,
        "profile": {"display_name": p.display_name, "colonies_total": p.colonies_total, "crops": [c.crop.name for c in p.crops]},
        "metrics": {"incoming_requests": len(reqs), "upcoming_services": len(upcoming), "awaiting_farmer": len(waiting),
                    "colonies_total": p.colonies_total},
        "requests": [booking_out(b) for b in reqs],
        "upcoming": [booking_out(b) for b in upcoming],
        "capacity_weeks": weekly,
        "recent": _recent(db, user),
    }


def buyer_dashboard(db: Session, user: User) -> dict:
    b = db.scalar(select(BuyerProfile).where(BuyerProfile.organization_id == user.organization_id))
    if not b:
        return {"role": "buyer", "profile_missing": True}
    today = local_today(get_settings().default_timezone)
    demands = db.scalars(select(BuyerDemand).where(BuyerDemand.buyer_id == b.id, BuyerDemand.status == DemandStatus.OPEN,
                                                   BuyerDemand.valid_until >= today).order_by(BuyerDemand.valid_until)).all()
    deliveries = [d for d in my_deliveries(db, user) if d["status"] == AssignmentStatus.ACTIVE]
    matching = matching_produce(db, user)
    return {
        "role": "buyer",
        "today": today,
        "profile": {"display_name": b.display_name, "buyer_type": b.buyer_type},
        "metrics": {
            "open_demands": len(demands),
            "open_demand_kg": float(sum((Decimal(str(demand_out(db, d)["remaining_kg"])) for d in demands), Decimal(0))),
            "active_deliveries": len(deliveries),
            "matching_batches": len(matching),
        },
        "demands": [demand_out(db, d) for d in demands],
        "deliveries": deliveries,
        "matching": matching,
        "recent": _recent(db, user),
    }


def reviewer_dashboard(db: Session, user: User) -> dict:
    waiting = db.scalars(select(CropObservation).where(CropObservation.review_status == ReviewStatus.AWAITING)
                         .order_by(CropObservation.observed_at)).all()
    mine = db.scalars(select(HumanReview).where(HumanReview.reviewer_id == user.id).order_by(HumanReview.created_at.desc()).limit(6)).all()
    return {
        "role": "reviewer",
        "metrics": {
            "awaiting_review": len(waiting),
            "uncertain": sum(1 for o in waiting if o.status == PredictionStatus.UNCERTAIN),
            "unsupported": sum(1 for o in waiting if o.status == PredictionStatus.UNSUPPORTED_INPUT),
            "my_reviews": db.scalar(select(func.count(HumanReview.id)).where(HumanReview.reviewer_id == user.id)),
        },
        "queue": [{**observation_brief(o), "cycle": _cycle_ctx(db.get(CropCycle, o.crop_cycle_id))} for o in waiting[:8]],
        "history": [{"id": r.id, "observation_id": r.observation_id, "decision": r.decision, "reviewed_label": r.reviewed_label,
                     "created_at": r.created_at} for r in mine],
        "recent": _recent(db, user),
    }


def admin_dashboard(db: Session, user: User) -> dict:
    from app.ml.crop_vision import get_model

    roles = dict(db.execute(select(User.role, func.count(User.id)).where(User.is_active.is_(True)).group_by(User.role)).all())
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(8)).all()
    return {
        "role": "admin",
        "metrics": {
            "active_users": sum(roles.values()),
            "unverified_labels": db.scalar(select(func.count(ProductLabel.id)).where(ProductLabel.verification_status == LabelVerification.UNVERIFIED)),
            "failed_predictions": db.scalar(select(func.count()).select_from(CropObservation).where(CropObservation.status == PredictionStatus.FAILED)),
        },
        "users_by_role": roles,
        "model": get_model().status(),
        "audit": [{"id": e.id, "action": e.action, "entity_type": e.entity_type, "entity_id": e.entity_id,
                   "actor": e.actor.full_name if e.actor else "System", "created_at": e.created_at, "severity": e.severity} for e in events],
        "recent": _recent(db, user),
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {
        Role.FARMER: farmer_dashboard,
        Role.PROVIDER: provider_dashboard,
        Role.BUYER: buyer_dashboard,
        Role.REVIEWER: reviewer_dashboard,
        Role.ADMIN: admin_dashboard,
    }[Role(user.role)](db, user)
