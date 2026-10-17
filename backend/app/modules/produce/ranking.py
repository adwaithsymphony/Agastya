"""Transparent buyer ranking for produce rerouting (rule-based scoring, not an ML prediction).

Hard constraints (any failure excludes the buyer):
  * buyer active, demand open and valid on the assessment date
  * same crop; batch grade accepted by the demand
  * remaining (unallocated) demand >= batch quantity
  * delivery window overlaps the batch's sell window [max(today, available_from), sell_by]
    where sell_by = deliver_by, else harvest + shelf life when shelf life is known
  * within the demand's max distance, when both locations are recorded
  * not the buyer whose assignment is being replaced

Ranking preferences (0-100):
  * timing 35   - how soon the buyer can receive, weighted more when the batch is urgent
  * distance 30 - straight-line km; neutral 15 when a location is missing
  * fit 25      - share of the buyer's remaining demand this batch fills (larger share preferred)
  * grade 10    - full marks when the buyer's top accepted grade equals the batch grade
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from app.core.geo import haversine_km

SCORING_VERSION = "br-1"


@dataclass
class BatchView:
    crop_id: int
    grade: str
    quantity_kg: Decimal
    harvested_on: date
    available_from: date
    deliver_by: date | None
    shelf_life_days: int | None
    latitude: float | None
    longitude: float | None


@dataclass
class DemandView:
    demand_id: int
    buyer_id: int
    buyer_name: str
    buyer_active: bool
    crop_id: int
    accepted_grades: list[str]
    remaining_kg: Decimal
    status: str
    valid_from: date
    valid_until: date
    delivery_start: date
    delivery_end: date
    max_distance_km: float | None
    latitude: float | None
    longitude: float | None


@dataclass
class Candidate:
    demand: DemandView
    eligible: bool
    score: float | None = None
    distance_km: float | None = None
    components: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    tradeoffs: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)


def sell_by(batch: BatchView) -> date | None:
    if batch.deliver_by:
        return batch.deliver_by
    if batch.shelf_life_days:
        return batch.harvested_on + timedelta(days=batch.shelf_life_days)
    return None


def urgency(batch: BatchView, today: date) -> tuple[str, int | None]:
    sb = sell_by(batch)
    if sb is None:
        return "unknown", None
    days = (sb - today).days
    if days <= 1:
        return "critical", days
    if days <= 3:
        return "high", days
    return "normal", days


def rank(batch: BatchView, demands: list[DemandView], today: date, *, exclude_buyer_id: int | None = None) -> list[Candidate]:
    start = max(today, batch.available_from)
    end = sell_by(batch)
    urg, days_left = urgency(batch, today)
    out: list[Candidate] = []
    for d in demands:
        c = Candidate(demand=d, eligible=False)
        c.distance_km = haversine_km(batch.latitude, batch.longitude, d.latitude, d.longitude)
        if d.buyer_id == exclude_buyer_id:
            c.exclusions.append("Buyer being replaced")
        if not d.buyer_active:
            c.exclusions.append("Buyer inactive")
        if d.status != "open" or not (d.valid_from <= today <= d.valid_until):
            c.exclusions.append("Demand not open today")
        if d.crop_id != batch.crop_id:
            c.exclusions.append("Different crop")
        if batch.grade not in d.accepted_grades:
            c.exclusions.append(f"Requires grade {'/'.join(d.accepted_grades)}")
        if d.remaining_kg < batch.quantity_kg:
            c.exclusions.append(f"Only {d.remaining_kg:,.0f} kg of demand left")
        if end is not None and end < start:
            c.exclusions.append("Batch is past its sell-by date")
        overlap_start = max(start, d.delivery_start)
        overlap_end = min(end, d.delivery_end) if end else d.delivery_end
        if overlap_end < overlap_start:
            c.exclusions.append("Delivery window does not fit")
        if d.max_distance_km is not None and c.distance_km is not None and c.distance_km > d.max_distance_km:
            c.exclusions.append(f"Beyond buyer's {d.max_distance_km:.0f} km limit")
        if c.exclusions:
            out.append(c)
            continue

        c.eligible = True
        earliest = max(overlap_start, d.delivery_start)
        wait = (earliest - start).days
        horizon = max(days_left if days_left is not None else 7, 1)
        timing = max(0.0, 1.0 - wait / horizon) if urg != "unknown" else max(0.0, 1.0 - wait / 7)
        timing_pts = 35.0 * timing
        if c.distance_km is not None:
            dist_pts = 30.0 * max(0.0, 1.0 - c.distance_km / 300.0)
        else:
            dist_pts = 15.0
        fill = float(batch.quantity_kg / d.remaining_kg) if d.remaining_kg else 0.0
        fit_pts = 25.0 * min(fill, 1.0)
        top_grade = min(d.accepted_grades)  # "A" < "B" < "C"
        grade_pts = 10.0 if top_grade == batch.grade else 5.0
        c.components = {
            "timing": round(timing_pts, 1),
            "distance": round(dist_pts, 1),
            "fit": round(fit_pts, 1),
            "grade": round(grade_pts, 1),
        }
        c.score = round(timing_pts + dist_pts + fit_pts + grade_pts, 1)

        c.reasons.append(f"Accepts grade {batch.grade}")
        if wait == 0:
            c.reasons.append(f"Can receive from {earliest:%d %b}")
        else:
            c.tradeoffs.append(f"Earliest delivery {earliest:%d %b} ({wait} day wait)")
        if c.distance_km is not None:
            (c.reasons if c.distance_km <= 120 else c.tradeoffs).append(f"{c.distance_km:.0f} km away (straight line)")
        else:
            c.tradeoffs.append("Distance unknown — location not recorded")
        c.reasons.append(f"{d.remaining_kg:,.0f} kg of open demand")
        if fill < 0.25:
            c.tradeoffs.append("Batch is a small share of this buyer's demand")
        if urg in ("critical", "high") and wait > 0:
            c.tradeoffs.append("Batch is urgent; any wait increases spoilage risk")
        out.append(c)

    out.sort(key=lambda c: (not c.eligible, -(c.score or 0), c.distance_km if c.distance_km is not None else 1e9))
    return out
