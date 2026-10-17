"""Unit tests for the deterministic pre-harvest-interval engine (no database)."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.modules.pesticide.engine import ApplicationInput, LabelRule, evaluate

IST = ZoneInfo("Asia/Kolkata")
TOMATO, CHILLI = 1, 2
P1, P2 = 10, 20


def rule(pid=P1, crop=TOMATO, phi=5, status="verified", vf=date(2024, 1, 1), vu=None, lid=1):
    return LabelRule(label_id=lid, product_id=pid, crop_id=crop, phi_days=phi, verification_status=status,
                     valid_from=vf, valid_until=vu, label_version="v1", source_reference="REF")


def app_(aid=1, pid=P1, when=datetime(2026, 3, 1, 8, 0, tzinfo=IST), crop=TOMATO, rec=None):
    return ApplicationInput(application_id=aid, product_id=pid, product_name=f"P{pid}", crop_id=crop, applied_at=when,
                            recorded_phi_days=rec)


def at_ist(y, m, d, hh=12):
    return datetime(y, m, d, hh, 0, tzinfo=IST)


def test_boundary_day_before_and_on_eligible_date():
    apps, rules = [app_()], [rule(phi=5)]
    before = evaluate(apps, rules, timezone="Asia/Kolkata", now=at_ist(2026, 3, 5), upcoming_window_days=0)
    assert before.status == "restricted"
    assert before.earliest_eligible_date == date(2026, 3, 6)
    assert before.days_until_eligible == 1
    on = evaluate(apps, rules, timezone="Asia/Kolkata", now=datetime(2026, 3, 6, 0, 0, tzinfo=IST))
    assert on.status == "eligible"


def test_upcoming_window():
    r = evaluate([app_()], [rule(phi=5)], timezone="Asia/Kolkata", now=at_ist(2026, 3, 3), upcoming_window_days=3)
    assert r.status == "upcoming" and r.days_until_eligible == 3
    r = evaluate([app_()], [rule(phi=5)], timezone="Asia/Kolkata", now=at_ist(2026, 3, 2), upcoming_window_days=3)
    assert r.status == "restricted"


def test_timezone_uses_local_application_date():
    # 20:00 UTC on 1 March is 01:30 IST on 2 March -> interval counts from 2 March.
    when = datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc)
    r = evaluate([app_(when=when)], [rule(phi=1)], timezone="Asia/Kolkata", now=at_ist(2026, 3, 2))
    assert r.earliest_eligible_date == date(2026, 3, 3)
    assert r.status == "upcoming"
    # Same instant evaluated for a farm in UTC counts from 1 March.
    r_utc = evaluate([app_(when=when)], [rule(phi=1)], timezone="UTC", now=datetime(2026, 3, 2, 12, tzinfo=timezone.utc))
    assert r_utc.earliest_eligible_date == date(2026, 3, 2)
    assert r_utc.status == "eligible"


def test_now_must_be_aware():
    with pytest.raises(ValueError):
        evaluate([], [], timezone="Asia/Kolkata", now=datetime(2026, 3, 1))


def test_multiple_applications_most_restrictive_governs():
    apps = [app_(1, P1, at_ist(2026, 3, 1)), app_(2, P2, at_ist(2026, 3, 4))]
    rules = [rule(P1, phi=10, lid=1), rule(P2, phi=2, lid=2)]
    r = evaluate(apps, rules, timezone="Asia/Kolkata", now=at_ist(2026, 3, 5))
    assert r.earliest_eligible_date == date(2026, 3, 11)
    assert r.governing_application_id == 1
    assert r.status == "restricted"


def test_no_applications_is_eligible_without_date():
    r = evaluate([], [], timezone="Asia/Kolkata", now=at_ist(2026, 3, 5))
    assert r.status == "eligible" and r.earliest_eligible_date is None and r.unresolved_count == 0


@pytest.mark.parametrize(
    "rules,issue",
    [
        ([], "no_label"),
        ([rule(crop=CHILLI)], "label_not_for_crop"),
        ([rule(status="unverified")], "label_unverified"),
        ([rule(status="rejected")], "label_rejected"),
        ([rule(vf=date(2020, 1, 1), vu=date(2025, 12, 31))], "label_not_valid_on_date"),
        ([rule(phi=None)], "invalid_interval"),
        ([rule(phi=3, lid=1), rule(phi=7, lid=2)], "conflicting_verified_labels"),
    ],
)
def test_missing_or_unverified_data_is_unknown(rules, issue):
    r = evaluate([app_()], rules, timezone="Asia/Kolkata", now=at_ist(2026, 4, 1))
    assert r.status == "unknown"
    assert r.unresolved_count == 1
    assert r.outcomes[0].issue == issue
    assert r.earliest_eligible_date is None


def test_unverified_label_never_sets_interval_even_if_verified_exists_for_other_crop():
    rules = [rule(crop=CHILLI, phi=1), rule(status="unverified", phi=0)]
    r = evaluate([app_()], rules, timezone="Asia/Kolkata", now=at_ist(2026, 3, 1, 9))
    assert r.status == "unknown"


def test_versioned_labels_select_rule_valid_on_application_date():
    rules = [rule(phi=1, vf=date(2022, 1, 1), vu=date(2025, 12, 31), lid=1), rule(phi=7, vf=date(2026, 1, 1), lid=2)]
    r = evaluate([app_()], rules, timezone="Asia/Kolkata", now=at_ist(2026, 3, 2))
    assert r.outcomes[0].label_id == 2 and r.earliest_eligible_date == date(2026, 3, 8)


def test_known_restriction_with_unresolved_stays_restricted_and_reports_unresolved():
    apps = [app_(1, P1), app_(2, P2)]
    r = evaluate(apps, [rule(P1, phi=10)], timezone="Asia/Kolkata", now=at_ist(2026, 3, 2))
    assert r.status == "restricted" and r.unresolved_count == 1


def test_elapsed_restriction_with_unresolved_is_unknown_not_eligible():
    apps = [app_(1, P1), app_(2, P2)]
    r = evaluate(apps, [rule(P1, phi=1)], timezone="Asia/Kolkata", now=at_ist(2026, 3, 20))
    assert r.status == "unknown"


def test_recorded_phi_longer_is_applied_shorter_is_ignored():
    longer = evaluate([app_(rec=9)], [rule(phi=5)], timezone="Asia/Kolkata", now=at_ist(2026, 3, 2))
    assert longer.earliest_eligible_date == date(2026, 3, 10)
    assert "recorded_phi_longer_applied" in longer.outcomes[0].warnings
    shorter = evaluate([app_(rec=1)], [rule(phi=5)], timezone="Asia/Kolkata", now=at_ist(2026, 3, 2))
    assert shorter.earliest_eligible_date == date(2026, 3, 6)
    assert "recorded_phi_shorter_ignored" in shorter.outcomes[0].warnings


def test_future_application_is_unresolved():
    r = evaluate([app_(when=at_ist(2026, 3, 10))], [rule()], timezone="Asia/Kolkata", now=at_ist(2026, 3, 5))
    assert r.status == "unknown" and r.outcomes[0].issue == "application_in_future"


def test_zero_day_phi_eligible_same_day():
    r = evaluate([app_()], [rule(phi=0)], timezone="Asia/Kolkata", now=at_ist(2026, 3, 1, 9))
    assert r.status == "eligible" and r.earliest_eligible_date == date(2026, 3, 1)


def test_month_and_leap_boundaries():
    r = evaluate([app_(when=at_ist(2028, 2, 27))], [rule(phi=3)], timezone="Asia/Kolkata", now=at_ist(2028, 2, 28))
    assert r.earliest_eligible_date == date(2028, 3, 1)
    assert (r.earliest_eligible_date - date(2028, 2, 27)) == timedelta(days=3)
