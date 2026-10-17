"""Provider matching and booking lifecycle rules for pollination services."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, InvalidTransition, Unprocessable
from app.core.geo import haversine_km
from app.modules.farms.models import CropCycle
from app.modules.pollination.models import (
    BookingStatus,
    PollinationBooking,
    ProviderAvailability,
    ProviderProfile,
)

MATCHING_VERSION = "pm-1"

# Allowed transitions: (from, to) -> roles that may perform it
TRANSITIONS: dict[tuple[str, str], set[str]] = {
    (BookingStatus.REQUESTED, BookingStatus.ACCEPTED): {"provider"},
    (BookingStatus.REQUESTED, BookingStatus.REJECTED): {"provider"},
    (BookingStatus.REQUESTED, BookingStatus.RESCHEDULE_PROPOSED): {"provider"},
    (BookingStatus.REQUESTED, BookingStatus.CANCELLED): {"farmer"},
    (BookingStatus.REQUESTED, BookingStatus.REQUESTED): {"farmer"},  # farmer edits requested dates
    (BookingStatus.RESCHEDULE_PROPOSED, BookingStatus.ACCEPTED): {"farmer"},  # farmer accepts proposal
    (BookingStatus.RESCHEDULE_PROPOSED, BookingStatus.CANCELLED): {"farmer"},
    (BookingStatus.RESCHEDULE_PROPOSED, BookingStatus.REQUESTED): {"farmer"},  # counter with new dates
    (BookingStatus.ACCEPTED, BookingStatus.COMPLETED): {"provider"},
    (BookingStatus.ACCEPTED, BookingStatus.CANCELLED): {"farmer", "provider"},
    (BookingStatus.ACCEPTED, BookingStatus.REQUESTED): {"farmer"},  # farmer reschedules: needs re-acceptance
}


def check_transition(booking: PollinationBooking, to: str, role: str) -> None:
    roles = TRANSITIONS.get((booking.status, to))
    if not roles or role not in roles:
        raise InvalidTransition(f"A {booking.status.replace('_', ' ')} booking cannot be changed to {to.replace('_', ' ')} by this account.")


def _days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def capacity_profile(db: Session, provider: ProviderProfile, start: date, end: date, *, exclude_booking_id: int | None = None):
    """Per-day (available, committed) colonies over [start, end]. Committed counts ACCEPTED bookings only."""
    windows = list(
        db.scalars(
            select(ProviderAvailability).where(
                ProviderAvailability.provider_id == provider.id,
                ProviderAvailability.start_date <= end,
                ProviderAvailability.end_date >= start,
            )
        )
    )
    bookings = list(
        db.scalars(
            select(PollinationBooking).where(
                PollinationBooking.provider_id == provider.id,
                PollinationBooking.status == BookingStatus.ACCEPTED,
                PollinationBooking.start_date <= end,
                PollinationBooking.end_date >= start,
            )
        )
    )
    out = {}
    for d in _days(start, end):
        avail = sum(w.colonies_available for w in windows if w.start_date <= d <= w.end_date)
        committed = sum(b.colonies_requested for b in bookings if b.start_date <= d <= b.end_date and b.id != exclude_booking_id)
        out[d] = (avail, committed)
    return out


def remaining_capacity(db: Session, provider: ProviderProfile, start: date, end: date, *, exclude_booking_id: int | None = None) -> int:
    prof = capacity_profile(db, provider, start, end, exclude_booking_id=exclude_booking_id)
    return min((a - c for a, c in prof.values()), default=0)


def ensure_capacity(db: Session, provider: ProviderProfile, start: date, end: date, colonies: int, *, exclude_booking_id=None):
    prof = capacity_profile(db, provider, start, end, exclude_booking_id=exclude_booking_id)
    short = [d for d, (a, c) in prof.items() if a - c < colonies]
    if short:
        first = short[0]
        a, c = prof[first]
        raise Conflict(
            f"Not enough colonies available on {first:%d %b %Y} ({max(a - c, 0)} free, {colonies} needed).",
            code="over_capacity",
        )


def ensure_no_overlap_for_cycle(db: Session, cycle_id: int, start: date, end: date, *, exclude_booking_id=None):
    stmt = select(PollinationBooking).where(
        PollinationBooking.crop_cycle_id == cycle_id,
        PollinationBooking.status.in_([BookingStatus.REQUESTED, BookingStatus.ACCEPTED, BookingStatus.RESCHEDULE_PROPOSED]),
        PollinationBooking.start_date <= end,
        PollinationBooking.end_date >= start,
    )
    if exclude_booking_id:
        stmt = stmt.where(PollinationBooking.id != exclude_booking_id)
    other = db.scalar(stmt)
    if other:
        raise Conflict(
            f"This crop cycle already has an open booking with {other.provider.display_name} for overlapping dates.",
            code="conflicting_booking",
        )


def validate_window(cycle: CropCycle, start: date, end: date, today: date) -> None:
    if end < start:
        raise Unprocessable("End date must be on or after start date.")
    if start < today:
        raise Unprocessable("Booking dates must be in the future.")
    if (end - start).days > 60:
        raise Unprocessable("A single booking can cover at most 60 days.")


@dataclass
class ProviderMatch:
    provider: ProviderProfile
    eligible: bool
    score: float | None
    distance_km: float | None
    free_colonies: int
    overlap_days: int
    window_days: int
    reasons: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)


def match_providers(
    db: Session, cycle: CropCycle, start: date, end: date, colonies: int | None
) -> list[ProviderMatch]:
    """Hard constraints: active, crop supported, serves the farm's area, availability covers the
    whole window with enough free colonies. Ranking (0-100): coverage 40, capacity headroom 20,
    distance 30 (only when both points have coordinates), same district 10."""
    farm = cycle.field.farm
    window_days = (end - start).days + 1
    results: list[ProviderMatch] = []
    for p in db.scalars(select(ProviderProfile).order_by(ProviderProfile.display_name)):
        dist = haversine_km(farm.latitude, farm.longitude, p.latitude, p.longitude)
        prof = capacity_profile(db, p, start, end)
        covered = [d for d, (a, _) in prof.items() if a > 0]
        free = min((a - c for a, c in prof.values()), default=0)
        m = ProviderMatch(p, False, None, dist, max(free, 0), len(covered), window_days)
        if not p.is_active:
            m.exclusions.append("Provider is not currently active")
        if cycle.crop_id not in {c.crop_id for c in p.crops}:
            m.exclusions.append(f"Does not list {cycle.crop.name}")
        in_area = any(a.district.lower() == farm.district.lower() and a.state.lower() == farm.state.lower() for a in p.service_areas)
        in_radius = dist is not None and p.service_radius_km is not None and dist <= p.service_radius_km
        if not (in_area or in_radius):
            m.exclusions.append(f"Does not serve {farm.district}")
        if len(covered) < window_days:
            m.exclusions.append(
                "No availability for these dates" if not covered else f"Available {len(covered)} of {window_days} days"
            )
        elif colonies is not None and free < colonies:
            m.exclusions.append(f"Only {max(free, 0)} colonies free ({colonies} needed)")
        if not m.exclusions:
            m.eligible = True
            score = 40.0 * len(covered) / window_days
            need = colonies or 1
            headroom = min(free / need, 3.0) / 3.0
            score += 20.0 * headroom
            if dist is not None:
                score += 30.0 * max(0.0, 1.0 - dist / 250.0)
                m.reasons.append(f"About {dist:.0f} km away (straight line)")
            else:
                score += 15.0
                m.reasons.append("Distance unknown — location not recorded")
            same_district = p.base_district.lower() == farm.district.lower()
            if same_district:
                score += 10.0
                m.reasons.insert(0, f"Based in {p.base_district}")
            elif in_area:
                m.reasons.insert(0, f"Serves {farm.district}")
            m.reasons.insert(0, f"Supports {cycle.crop.name}")
            m.reasons.append(f"{free} colonies free across the whole window")
            m.score = round(score, 1)
        results.append(m)
    results.sort(key=lambda r: (not r.eligible, -(r.score or 0), r.provider.display_name))
    return results
