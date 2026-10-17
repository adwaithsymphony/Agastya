from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import local_today, now_utc
from app.core.errors import Conflict, InvalidTransition, NotFound, Unprocessable
from app.core.events import audit, notify, org_user_ids
from app.modules.identity.models import Role, User
from app.modules.produce import ranking
from app.modules.produce.models import (
    AssignmentStatus,
    BatchAssignment,
    BatchStatus,
    BuyerDemand,
    BuyerMatch,
    BuyerProfile,
    ProduceBatch,
    RerouteRun,
    RerouteTrigger,
    Shipment,
    ShipmentEvent,
    ShipmentStatus,
)

ALLOCATING = (AssignmentStatus.ACTIVE, AssignmentStatus.COMPLETED)
REROUTABLE = (BatchStatus.UNASSIGNED, BatchStatus.NEEDS_DESTINATION, BatchStatus.ASSIGNED, BatchStatus.IN_TRANSIT)


def allocated_kg(db: Session, demand_id: int) -> Decimal:
    v = db.scalar(
        select(func.coalesce(func.sum(BatchAssignment.quantity_kg), 0)).where(
            BatchAssignment.demand_id == demand_id, BatchAssignment.status.in_(ALLOCATING)
        )
    )
    return Decimal(v or 0)


def remaining_kg(db: Session, demand: BuyerDemand) -> Decimal:
    return max(Decimal(demand.quantity_kg) - allocated_kg(db, demand.id), Decimal(0))


def batch_tz(batch: ProduceBatch) -> str:
    if batch.crop_cycle is not None:
        return batch.crop_cycle.field.farm.timezone
    return "Asia/Kolkata"


def batch_view(batch: ProduceBatch) -> ranking.BatchView:
    farm = batch.crop_cycle.field.farm if batch.crop_cycle else None
    return ranking.BatchView(
        crop_id=batch.crop_id,
        grade=batch.grade,
        quantity_kg=Decimal(batch.quantity_kg),
        harvested_on=batch.harvested_on,
        available_from=batch.available_from,
        deliver_by=batch.deliver_by,
        shelf_life_days=batch.shelf_life_days,
        latitude=farm.latitude if farm else None,
        longitude=farm.longitude if farm else None,
    )


def demand_view(db: Session, d: BuyerDemand) -> ranking.DemandView:
    b = d.buyer
    return ranking.DemandView(
        demand_id=d.id,
        buyer_id=b.id,
        buyer_name=b.display_name,
        buyer_active=b.is_active,
        crop_id=d.crop_id,
        accepted_grades=list(d.accepted_grades),
        remaining_kg=remaining_kg(db, d),
        status=d.status,
        valid_from=d.valid_from,
        valid_until=d.valid_until,
        delivery_start=d.delivery_start,
        delivery_end=d.delivery_end,
        max_distance_km=d.max_distance_km,
        latitude=b.latitude,
        longitude=b.longitude,
    )


def active_assignment(batch: ProduceBatch) -> BatchAssignment | None:
    return next((a for a in batch.assignments if a.status == AssignmentStatus.ACTIVE), None)


def start_reroute(db: Session, user: User, batch: ProduceBatch, trigger: str, note: str | None) -> RerouteRun:
    if batch.status not in REROUTABLE:
        raise InvalidTransition(f"A {batch.status.replace('_', ' ')} batch cannot be rerouted.")
    today = local_today(batch_tz(batch))
    current = active_assignment(batch)
    if trigger == RerouteTrigger.DISRUPTION:
        if not note:
            raise Unprocessable("Describe the disruption.")
        if batch.status != BatchStatus.NEEDS_DESTINATION:
            prev = batch.status
            batch.status = BatchStatus.NEEDS_DESTINATION
            audit(db, actor_id=user.id, action="batch.disruption_reported", entity_type="produce_batch", entity_id=batch.id,
                  before={"status": prev}, after={"status": batch.status, "note": note})
    run = RerouteRun(batch_id=batch.id, trigger=trigger, note=note, triggered_by=user.id, as_of_date=today,
                     scoring_version=ranking.SCORING_VERSION)
    db.add(run)
    db.flush()
    demands = db.scalars(select(BuyerDemand).where(BuyerDemand.crop_id == batch.crop_id)).all()
    views = [demand_view(db, d) for d in demands]
    exclude = current.buyer_id if current else None
    if exclude is None and trigger == RerouteTrigger.BUYER_CANCELLED:
        last_cancel = next((a for a in batch.assignments if a.status == AssignmentStatus.CANCELLED_BY_BUYER), None)
        exclude = last_cancel.buyer_id if last_cancel else None
    candidates = ranking.rank(batch_view(batch), views, today, exclude_buyer_id=exclude)
    r = 0
    for c in candidates:
        if c.eligible:
            r += 1
        db.add(
            BuyerMatch(
                run_id=run.id,
                batch_id=batch.id,
                demand_id=c.demand.demand_id,
                buyer_id=c.demand.buyer_id,
                eligible=c.eligible,
                score=c.score,
                rank=r if c.eligible else None,
                distance_km=c.distance_km,
                remaining_demand_kg=c.demand.remaining_kg,
                components=c.components,
                reasons=c.reasons,
                tradeoffs=c.tradeoffs,
                exclusions=c.exclusions,
            )
        )
    audit(db, actor_id=user.id, action="batch.reroute_requested", entity_type="produce_batch", entity_id=batch.id,
          after={"run_id": run.id, "trigger": trigger, "eligible": r, "considered": len(candidates)})
    db.flush()
    return run


def confirm_destination(db: Session, user: User, batch_id: int, match_id: int, expected_version: int) -> ProduceBatch:
    batch = db.scalar(select(ProduceBatch).where(ProduceBatch.id == batch_id).with_for_update(of=ProduceBatch))
    if not batch:
        raise NotFound("Batch not found.")
    if batch.organization_id != user.organization_id:
        raise NotFound("Batch not found.")
    if batch.version != expected_version:
        raise Conflict("This batch changed since you loaded it. Review the latest options.", code="stale_version")
    if batch.status not in REROUTABLE:
        raise InvalidTransition(f"A {batch.status.replace('_', ' ')} batch cannot be assigned.")
    match = db.get(BuyerMatch, match_id)
    if not match or match.batch_id != batch.id:
        raise NotFound("Recommendation not found.")
    latest_run = db.scalar(select(func.max(RerouteRun.id)).where(RerouteRun.batch_id == batch.id))
    if match.run_id != latest_run:
        raise Conflict("These recommendations are out of date. Refresh the options.", code="stale_recommendations")
    if not match.eligible:
        raise Unprocessable("This buyer does not meet the batch's requirements.")

    demand = db.scalar(select(BuyerDemand).where(BuyerDemand.id == match.demand_id).with_for_update(of=BuyerDemand))
    today = local_today(batch_tz(batch))
    current = active_assignment(batch)
    # Re-check hard constraints at confirmation time (demand may have changed since ranking).
    recheck = ranking.rank(batch_view(batch), [demand_view(db, demand)], today,
                           exclude_buyer_id=current.buyer_id if current else None)
    if not recheck[0].eligible:
        raise Conflict("This buyer can no longer take the batch: " + "; ".join(recheck[0].exclusions), code="no_longer_eligible")

    prev_status = batch.status
    previous_buyer = None
    if current:
        previous_buyer = current.buyer
        current.status = AssignmentStatus.SUPERSEDED
        current.ended_at = now_utc()
        current.ended_by = user.id
        current.end_reason = "Replaced by a new destination"
        if current.shipment and current.shipment.status in (ShipmentStatus.SCHEDULED, ShipmentStatus.DISPATCHED):
            current.shipment.status = ShipmentStatus.CANCELLED
            db.add(ShipmentEvent(shipment_id=current.shipment.id, status=ShipmentStatus.CANCELLED, note="Destination changed", actor_id=user.id))
        db.flush()

    run = db.get(RerouteRun, match.run_id)
    reason = {"buyer_cancelled": "reroute_buyer_cancelled", "disruption": "reroute_disruption"}.get(run.trigger, "initial")
    if reason == "initial" and any(a.status != AssignmentStatus.ACTIVE for a in batch.assignments):
        reason = "reassigned"
    a = BatchAssignment(
        batch_id=batch.id,
        buyer_id=match.buyer_id,
        demand_id=demand.id,
        match_id=match.id,
        quantity_kg=batch.quantity_kg,
        status=AssignmentStatus.ACTIVE,
        reason=reason,
        assigned_by=user.id,
    )
    db.add(a)
    db.flush()
    scheduled = max(today, demand.delivery_start, batch.available_from)
    sh = Shipment(batch_id=batch.id, assignment_id=a.id, status=ShipmentStatus.SCHEDULED, scheduled_date=scheduled)
    db.add(sh)
    db.flush()
    db.add(ShipmentEvent(shipment_id=sh.id, status=ShipmentStatus.SCHEDULED, note=f"Delivery to {match.buyer.display_name}", actor_id=user.id))
    batch.status = BatchStatus.ASSIGNED
    batch.updated_at = now_utc()
    audit(db, actor_id=user.id, action="batch.destination_assigned", entity_type="produce_batch", entity_id=batch.id,
          before={"status": prev_status, "buyer": previous_buyer.display_name if previous_buyer else None},
          after={"status": batch.status, "buyer": match.buyer.display_name, "assignment_id": a.id, "score": match.score})

    qty = f"{batch.quantity_kg:,.0f} kg"
    notify(db, org_user_ids(db, match.buyer.organization_id, Role.BUYER), event_type="batch.assigned_to_you",
           title=f"Incoming {batch.crop.name}: {qty}", body=f"Batch {batch.code}, grade {batch.grade}. Scheduled {scheduled:%d %b}.",
           entity_type="produce_batch", entity_id=batch.id, link="/app/buyer/deliveries")
    if previous_buyer and previous_buyer.id != match.buyer_id:
        notify(db, org_user_ids(db, previous_buyer.organization_id, Role.BUYER), event_type="batch.reassigned_away",
               title=f"Batch {batch.code} redirected", body="This delivery has been reassigned to another buyer.",
               entity_type="produce_batch", entity_id=batch.id, link="/app/buyer/deliveries", severity="warning")
    notify(db, org_user_ids(db, batch.organization_id, Role.FARMER), event_type="batch.destination_confirmed",
           title=f"{batch.code} assigned to {match.buyer.display_name}", body=f"{qty} scheduled for {scheduled:%d %b}.",
           entity_type="produce_batch", entity_id=batch.id, link=f"/app/batches/{batch.id}", exclude_user_id=user.id)
    return batch


def buyer_cancel(db: Session, user: User, assignment_id: int, reason: str) -> BatchAssignment:
    a = db.get(BatchAssignment, assignment_id)
    if not a or a.buyer.organization_id != user.organization_id:
        raise NotFound("Delivery not found.")
    batch = db.scalar(select(ProduceBatch).where(ProduceBatch.id == a.batch_id).with_for_update(of=ProduceBatch))
    if a.status != AssignmentStatus.ACTIVE:
        raise InvalidTransition("Only active deliveries can be cancelled.")
    if a.shipment and a.shipment.status == ShipmentStatus.DELIVERED:
        raise InvalidTransition("This delivery is already complete.")
    a.status = AssignmentStatus.CANCELLED_BY_BUYER
    a.ended_at = now_utc()
    a.ended_by = user.id
    a.end_reason = reason
    if a.shipment and a.shipment.status in (ShipmentStatus.SCHEDULED, ShipmentStatus.DISPATCHED):
        a.shipment.status = ShipmentStatus.CANCELLED
        db.add(ShipmentEvent(shipment_id=a.shipment.id, status=ShipmentStatus.CANCELLED, note=f"Buyer cancelled: {reason}", actor_id=user.id))
    prev = batch.status
    batch.status = BatchStatus.NEEDS_DESTINATION
    batch.updated_at = now_utc()
    audit(db, actor_id=user.id, action="assignment.cancelled_by_buyer", entity_type="produce_batch", entity_id=batch.id,
          before={"status": prev, "assignment": a.id}, after={"status": batch.status, "reason": reason}, severity="warning")
    notify(db, org_user_ids(db, batch.organization_id, Role.FARMER), event_type="batch.buyer_cancelled",
           title=f"{a.buyer.display_name} cancelled {batch.code}",
           body=f"{batch.quantity_kg:,.0f} kg {batch.crop.name} needs a new destination. Reason: {reason}",
           entity_type="produce_batch", entity_id=batch.id, link=f"/app/batches/{batch.id}", severity="warning")
    return a


SHIPMENT_FLOW = {
    ShipmentStatus.SCHEDULED: {ShipmentStatus.DISPATCHED: Role.FARMER},
    ShipmentStatus.DISPATCHED: {ShipmentStatus.DELIVERED: Role.BUYER},
}


def advance_shipment(db: Session, user: User, shipment_id: int, to: str, note: str | None) -> Shipment:
    sh = db.get(Shipment, shipment_id)
    if not sh:
        raise NotFound("Shipment not found.")
    a = sh.assignment
    batch = db.scalar(select(ProduceBatch).where(ProduceBatch.id == sh.batch_id).with_for_update(of=ProduceBatch))
    owner_ok = (user.role == Role.FARMER and batch.organization_id == user.organization_id) or (
        user.role == Role.BUYER and a.buyer.organization_id == user.organization_id
    )
    if not owner_ok:
        raise NotFound("Shipment not found.")
    allowed = SHIPMENT_FLOW.get(ShipmentStatus(sh.status), {})
    if to not in allowed or allowed[ShipmentStatus(to)] != user.role:
        raise InvalidTransition(f"A {sh.status} shipment cannot be marked {to} by this account.")
    if a.status != AssignmentStatus.ACTIVE:
        raise InvalidTransition("This delivery is no longer active.")
    sh.status = to
    db.add(ShipmentEvent(shipment_id=sh.id, status=to, note=note, actor_id=user.id))
    prev = batch.status
    if to == ShipmentStatus.DISPATCHED:
        batch.status = BatchStatus.IN_TRANSIT
        notify(db, org_user_ids(db, a.buyer.organization_id, Role.BUYER), event_type="shipment.dispatched",
               title=f"{batch.code} dispatched", body=f"{batch.quantity_kg:,.0f} kg {batch.crop.name} is on its way.",
               entity_type="produce_batch", entity_id=batch.id, link="/app/buyer/deliveries")
    elif to == ShipmentStatus.DELIVERED:
        batch.status = BatchStatus.DELIVERED
        a.status = AssignmentStatus.COMPLETED
        a.ended_at = now_utc()
        a.ended_by = user.id
        a.end_reason = "Delivered"
        notify(db, org_user_ids(db, batch.organization_id, Role.FARMER), event_type="shipment.delivered",
               title=f"{batch.code} received by {a.buyer.display_name}", entity_type="produce_batch", entity_id=batch.id,
               link=f"/app/batches/{batch.id}")
    batch.updated_at = now_utc()
    audit(db, actor_id=user.id, action=f"shipment.{to}", entity_type="produce_batch", entity_id=batch.id,
          before={"status": prev}, after={"status": batch.status, "shipment": sh.id})
    return sh
