from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now_utc
from app.core.config import get_settings
from app.core.events import notify, org_user_ids
from app.modules.farms.models import CropCycle
from app.modules.identity.models import Role
from app.modules.pesticide import engine
from app.modules.pesticide.models import (
    ApplicationStatus,
    LabelSource,
    LabelVerification,
    HarvestAssessment,
    PesticideApplication,
    ProductLabel,
)


SAMPLE_REGISTRANT = "Demonstration record"  # set only by app.seed on fictional products


def label_provenance(lbl: ProductLabel) -> str:
    """One provenance vocabulary for every screen. Rules seeded as samples, and any rule for a
    fictional sample product, stay "fictional_sample" even after an administrator verifies them."""
    if lbl.source_kind == LabelSource.DEMO_SEED or (lbl.product is not None and lbl.product.registrant == SAMPLE_REGISTRANT):
        return "fictional_sample"
    return "reference" if lbl.verification_status == LabelVerification.VERIFIED else "submitted"


def _inputs(db: Session, cycle: CropCycle, *, applied_before: datetime | None = None):
    db.flush()  # the session does not autoflush; pending changes must be visible to the queries below
    stmt = select(PesticideApplication).where(
        PesticideApplication.crop_cycle_id == cycle.id, PesticideApplication.status == ApplicationStatus.ACTIVE
    )
    apps = list(db.scalars(stmt))
    if applied_before is not None:
        apps = [a for a in apps if a.applied_at <= applied_before]
    product_ids = {a.product_id for a in apps}
    rules = []
    if product_ids:
        for lbl in db.scalars(select(ProductLabel).where(ProductLabel.product_id.in_(product_ids))):
            rules.append(
                engine.LabelRule(
                    label_id=lbl.id,
                    product_id=lbl.product_id,
                    crop_id=lbl.crop_id,
                    phi_days=lbl.phi_days,
                    verification_status=lbl.verification_status,
                    valid_from=lbl.valid_from,
                    valid_until=lbl.valid_until,
                    label_version=lbl.label_version,
                    source_reference=lbl.source_reference,
                    provenance=label_provenance(lbl),
                )
            )
    inputs = [
        engine.ApplicationInput(
            application_id=a.id,
            product_id=a.product_id,
            product_name=a.product.trade_name,
            crop_id=cycle.crop_id,
            applied_at=a.applied_at,
            recorded_phi_days=a.recorded_phi_days,
        )
        for a in apps
    ]
    return inputs, rules


def evaluate_cycle(db: Session, cycle: CropCycle, *, now: datetime | None = None) -> engine.Assessment:
    inputs, rules = _inputs(db, cycle)
    return engine.evaluate(
        inputs,
        rules,
        timezone=cycle.field.farm.timezone,
        now=now or now_utc(),
        upcoming_window_days=get_settings().harvest_upcoming_window_days,
    )


def evaluate_for_harvest_date(db: Session, cycle: CropCycle, harvest_date) -> engine.Assessment:
    """Eligibility as it stood at the end of a given local harvest date (applications up to then)."""
    tz = ZoneInfo(cycle.field.farm.timezone)
    as_of = datetime.combine(harvest_date, time(23, 59, 59), tzinfo=tz)
    inputs, rules = _inputs(db, cycle, applied_before=as_of)
    return engine.evaluate(inputs, rules, timezone=cycle.field.farm.timezone, now=as_of, upcoming_window_days=0)


def record_assessment(
    db: Session, cycle: CropCycle, *, trigger: str, actor_id: int | None, notify_change: bool = True
) -> tuple[engine.Assessment, HarvestAssessment | None]:
    """Persist a snapshot when the status or earliest date changed since the last snapshot."""
    result = evaluate_cycle(db, cycle)
    last = db.scalar(
        select(HarvestAssessment)
        .where(HarvestAssessment.crop_cycle_id == cycle.id)
        .order_by(HarvestAssessment.id.desc())
        .limit(1)
    )
    changed = (
        last is None
        or last.status != result.status
        or last.earliest_eligible_date != result.earliest_eligible_date
        or last.unresolved_count != result.unresolved_count
    )
    if not changed:
        return result, None
    snap = HarvestAssessment(
        crop_cycle_id=cycle.id,
        status=result.status,
        as_of_date=result.as_of_date,
        earliest_eligible_date=result.earliest_eligible_date,
        governing_application_id=result.governing_application_id,
        unresolved_count=result.unresolved_count,
        timezone=result.timezone,
        rule_version=result.rule_version,
        trigger=trigger,
        details=result.details(),
        computed_by=actor_id,
    )
    db.add(snap)
    db.flush()
    if notify_change and last is not None and last.status != result.status:
        title = {
            "restricted": f"{cycle.crop.name}: harvest restricted",
            "upcoming": f"{cycle.crop.name}: harvest eligibility soon",
            "eligible": f"{cycle.crop.name}: eligible under recorded PHI rules",
            "unknown": f"{cycle.crop.name}: harvest eligibility needs verification",
        }[result.status]
        body = (
            f"Earliest eligible date {result.earliest_eligible_date:%d %b %Y}."
            if result.earliest_eligible_date and result.status in ("restricted", "upcoming")
            else None
        )
        notify(
            db,
            org_user_ids(db, cycle.field.farm.organization_id, Role.FARMER),
            event_type="harvest.status_changed",
            title=title,
            body=body,
            entity_type="crop_cycle",
            entity_id=cycle.id,
            link=f"/app/harvest?cycle={cycle.id}",
            severity="warning" if result.status in ("restricted", "unknown") else "info",
        )
    return result, snap


def assessment_out(result: engine.Assessment, apps_by_id: dict[int, PesticideApplication] | None = None) -> dict:
    outcomes = []
    for o in result.outcomes:
        d = o.to_dict()
        d["issue_message"] = engine.ISSUE_MESSAGES.get(o.issue) if o.issue else None
        outcomes.append(d)
    return {
        "status": result.status,
        "as_of_date": result.as_of_date,
        "timezone": result.timezone,
        "earliest_eligible_date": result.earliest_eligible_date,
        "days_until_eligible": result.days_until_eligible,
        "governing_application_id": result.governing_application_id,
        "unresolved_count": result.unresolved_count,
        "rule_version": result.rule_version,
        "uses_fictional_reference": result.uses_fictional_reference,
        "outcomes": outcomes,
    }


def recompute_for_product(db: Session, product_id: int, *, actor_id: int | None, trigger: str) -> int:
    cycles = db.scalars(
        select(CropCycle)
        .join(PesticideApplication, PesticideApplication.crop_cycle_id == CropCycle.id)
        .where(PesticideApplication.product_id == product_id)
        .distinct()
    ).all()
    for c in cycles:
        record_assessment(db, c, trigger=trigger, actor_id=actor_id)
    return len(cycles)


def default_application_window() -> timedelta:
    return timedelta(days=365)
