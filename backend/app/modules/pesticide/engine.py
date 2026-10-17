"""Deterministic harvest-eligibility engine (pre-harvest interval rules).

Rule semantics (RULE_VERSION "phi-1"):
  * Only VERIFIED label rules for the same product AND crop, valid on the application's local date,
    are authoritative. Unverified, rejected, expired or other-crop labels never set the interval.
  * Application date = the application's timestamp converted to the farm's time zone.
  * Earliest eligible harvest date = application local date + PHI calendar days.
    Harvest is permitted from 00:00 local time on that date.
  * If the farmer recorded a longer PHI than the verified label, the longer (more restrictive)
    value is used and flagged. A shorter recorded value never shortens the verified interval.
  * Two verified rules for the same product/crop/date with different PHI values are a conflict:
    the application is unresolved until reference data is corrected.
  * The most restrictive (latest) date across all resolved applications governs.
  * Overall status:
      restricted - a known interval ends more than `upcoming_window_days` from today
      upcoming   - a known interval ends within `upcoming_window_days`
      unknown    - no known restriction remains, but one or more applications are unresolved
      eligible   - every recorded application is resolved and all intervals have elapsed
    "eligible" means eligible according to recorded PHI rules only; it is not a safety or
    compliance guarantee.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

RULE_VERSION = "phi-1"


@dataclass(frozen=True)
class LabelRule:
    label_id: int
    product_id: int
    crop_id: int
    phi_days: int | None
    verification_status: str
    valid_from: date
    valid_until: date | None
    label_version: str
    source_reference: str
    # "reference" for real label data; "fictional_sample" for seeded sample rules, which may be
    # marked verified for workflow testing but must never be presented as agricultural guidance.
    provenance: str = "reference"


@dataclass(frozen=True)
class ApplicationInput:
    application_id: int
    product_id: int
    product_name: str
    crop_id: int
    applied_at: datetime
    recorded_phi_days: int | None = None


@dataclass
class ApplicationOutcome:
    application_id: int
    product_name: str
    application_date: date
    resolved: bool
    phi_days: int | None = None
    earliest_eligible_date: date | None = None
    label_id: int | None = None
    label_version: str | None = None
    source_reference: str | None = None
    issue: str | None = None
    warnings: list[str] = field(default_factory=list)
    provenance: str | None = None

    def to_dict(self) -> dict:
        return {
            "application_id": self.application_id,
            "product_name": self.product_name,
            "application_date": self.application_date.isoformat(),
            "resolved": self.resolved,
            "phi_days": self.phi_days,
            "earliest_eligible_date": self.earliest_eligible_date.isoformat() if self.earliest_eligible_date else None,
            "label_id": self.label_id,
            "label_version": self.label_version,
            "source_reference": self.source_reference,
            "issue": self.issue,
            "warnings": self.warnings,
            "provenance": self.provenance,
        }


@dataclass
class Assessment:
    status: str
    as_of_date: date
    timezone: str
    earliest_eligible_date: date | None
    days_until_eligible: int | None
    governing_application_id: int | None
    unresolved_count: int
    outcomes: list[ApplicationOutcome]
    rule_version: str = RULE_VERSION

    @property
    def uses_fictional_reference(self) -> bool:
        return any(o.resolved and o.provenance == "fictional_sample" for o in self.outcomes)

    def details(self) -> dict:
        return {
            "outcomes": [o.to_dict() for o in self.outcomes],
            "rule_version": self.rule_version,
            "uses_fictional_reference": self.uses_fictional_reference,
        }


ISSUE_MESSAGES = {
    "no_label": "No label rule on record for this product.",
    "label_not_for_crop": "No label rule for this product on this crop.",
    "label_unverified": "Label rule awaiting verification against an authoritative source.",
    "label_rejected": "Label rule was rejected during verification.",
    "label_not_valid_on_date": "No verified label rule was valid on the application date.",
    "conflicting_verified_labels": "Verified label rules disagree on the pre-harvest interval.",
    "invalid_interval": "Verified label rule has no valid pre-harvest interval.",
    "application_in_future": "Application time is later than the assessment time.",
}


def _resolve(app: ApplicationInput, rules: list[LabelRule], tz: ZoneInfo, now_local_date: date) -> ApplicationOutcome:
    app_date = app.applied_at.astimezone(tz).date()
    out = ApplicationOutcome(app.application_id, app.product_name, app_date, resolved=False)
    if app_date > now_local_date:
        out.issue = "application_in_future"
        return out

    product_rules = [r for r in rules if r.product_id == app.product_id]
    crop_rules = [r for r in product_rules if r.crop_id == app.crop_id]
    if not product_rules:
        out.issue = "no_label"
        return out
    if not crop_rules:
        out.issue = "label_not_for_crop"
        return out

    verified = [r for r in crop_rules if r.verification_status == "verified"]
    valid = [r for r in verified if r.valid_from <= app_date and (r.valid_until is None or r.valid_until >= app_date)]
    if not valid:
        if verified:
            out.issue = "label_not_valid_on_date"
        elif any(r.verification_status == "unverified" for r in crop_rules):
            out.issue = "label_unverified"
        else:
            out.issue = "label_rejected"
        return out

    phis = {r.phi_days for r in valid}
    if len(phis) > 1:
        out.issue = "conflicting_verified_labels"
        return out
    rule = max(valid, key=lambda r: r.valid_from)
    if rule.phi_days is None or rule.phi_days < 0:
        out.issue = "invalid_interval"
        out.label_id = rule.label_id
        return out

    phi = rule.phi_days
    if app.recorded_phi_days is not None and app.recorded_phi_days != rule.phi_days:
        if app.recorded_phi_days > rule.phi_days:
            out.warnings.append("recorded_phi_longer_applied")
            phi = app.recorded_phi_days
        else:
            out.warnings.append("recorded_phi_shorter_ignored")

    out.resolved = True
    out.phi_days = phi
    out.earliest_eligible_date = app_date + timedelta(days=phi)
    out.label_id = rule.label_id
    out.label_version = rule.label_version
    out.source_reference = rule.source_reference
    out.provenance = rule.provenance
    return out


def evaluate(
    applications: list[ApplicationInput],
    rules: list[LabelRule],
    *,
    timezone: str,
    now: datetime,
    upcoming_window_days: int = 3,
) -> Assessment:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    tz = ZoneInfo(timezone)
    today = now.astimezone(tz).date()
    outcomes = [_resolve(a, rules, tz, today) for a in sorted(applications, key=lambda a: a.applied_at)]
    resolved = [o for o in outcomes if o.resolved]
    unresolved = [o for o in outcomes if not o.resolved]

    earliest = max((o.earliest_eligible_date for o in resolved), default=None)
    governing = None
    if earliest is not None:
        governing = max(
            (o for o in resolved if o.earliest_eligible_date == earliest), key=lambda o: o.application_date
        ).application_id

    if earliest is not None and earliest > today:
        days = (earliest - today).days
        status = "upcoming" if days <= upcoming_window_days else "restricted"
    elif unresolved:
        status, days = "unknown", None
    else:
        status, days = "eligible", 0 if earliest is not None else None

    return Assessment(
        status=status,
        as_of_date=today,
        timezone=timezone,
        earliest_eligible_date=earliest,
        days_until_eligible=days if status in ("restricted", "upcoming") else (0 if status == "eligible" and earliest else None),
        governing_application_id=governing,
        unresolved_count=len(unresolved),
        outcomes=outcomes,
    )
