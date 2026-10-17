from datetime import timedelta

from tests.conftest import TODAY, Client, cycle_id


def d(n):
    return str(TODAY + timedelta(days=n))


def test_matching_explains_inclusions_and_exclusions(farmer):
    mustard = cycle_id(farmer, "Mustard")
    res = farmer.get(f"/api/v1/pollination/providers/match?crop_cycle_id={mustard}&start_date={d(24)}&end_date={d(40)}&colonies=6").json()
    by = {r["provider"]["display_name"]: r for r in res}
    assert by["Madhuban Apiaries"]["eligible"] and by["Madhuban Apiaries"]["reasons"]
    assert by["Deccan Pollination Services"]["eligible"]
    kullu = by["Kullu Valley Beekeepers"]
    assert not kullu["eligible"] and any("Nashik" in e for e in kullu["exclusions"])
    assert res[0]["eligible"]  # eligible providers ranked first
    # Deccan is only available from day 20 -> partial coverage for an earlier window
    early = farmer.get(f"/api/v1/pollination/providers/match?crop_cycle_id={mustard}&start_date={d(10)}&end_date={d(25)}").json()
    deccan = next(r for r in early if r["provider"]["display_name"] == "Deccan Pollination Services")
    assert not deccan["eligible"] and "Available" in deccan["exclusions"][0]


def _madhuban_id(farmer):
    return next(p["id"] for p in farmer.get("/api/v1/pollination/providers").json() if p["display_name"] == "Madhuban Apiaries")


def test_booking_lifecycle_request_accept_complete(farmer, provider):
    mustard = cycle_id(farmer, "Mustard")
    pid = _madhuban_id(farmer)
    r = farmer.post("/api/v1/pollination/bookings", json={"crop_cycle_id": mustard, "provider_id": pid, "start_date": d(24),
                                                          "end_date": d(40), "colonies_requested": 8})
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["status"] == "requested"
    # provider sees it with a notification
    assert any(x["id"] == b["id"] for x in provider.get("/api/v1/pollination/bookings?status=requested").json())
    assert any(n["event_type"] == "booking.requested" for n in provider.get("/api/v1/notifications").json()["items"])
    # farmer cannot accept their own request
    bad = farmer.post(f"/api/v1/pollination/bookings/{b['id']}/transition", json={"to": "accepted", "version": b["version"]})
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "invalid_transition"
    acc = provider.post(f"/api/v1/pollination/bookings/{b['id']}/transition", json={"to": "accepted", "version": b["version"]})
    assert acc.status_code == 200 and acc.json()["status"] == "accepted"
    # stale version is rejected
    stale = provider.post(f"/api/v1/pollination/bookings/{b['id']}/transition", json={"to": "completed", "version": b["version"]})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "stale_version"
    # cannot complete before window starts
    early = provider.post(f"/api/v1/pollination/bookings/{b['id']}/transition", json={"to": "completed", "version": acc.json()["version"]})
    assert early.status_code == 409
    events = farmer.get(f"/api/v1/pollination/bookings/{b['id']}").json()["events"]
    assert [e["to"] for e in events] == ["requested", "accepted"]


def test_capacity_is_enforced_on_accept(db_seeded):
    farmer = Client().login("ramesh@agastya.demo")
    other = Client().login("sunita@agastya.demo")
    provider = Client().login("anil@agastya.demo")
    pid = _madhuban_id(farmer)
    # Madhuban: 80 colonies available; 4 already accepted for sunflower (days 8-20).
    mustard = cycle_id(farmer, "Mustard")
    r1 = farmer.post("/api/v1/pollination/bookings", json={"crop_cycle_id": mustard, "provider_id": pid, "start_date": d(24),
                                                           "end_date": d(40), "colonies_requested": 60}).json()
    # Sunita's seeded request (6 colonies, days 15-32): reschedule-free accept works first
    theirs = other.get("/api/v1/pollination/bookings").json()[0]
    ok = provider.post(f"/api/v1/pollination/bookings/{theirs['id']}/transition", json={"to": "accepted", "version": theirs["version"]})
    assert ok.status_code == 200
    ok2 = provider.post(f"/api/v1/pollination/bookings/{r1['id']}/transition", json={"to": "accepted", "version": r1["version"]})
    assert ok2.status_code == 200  # 60 + 6 = 66 <= 80
    # a further 20-colony request overlapping now exceeds remaining capacity at request time
    sunflower = cycle_id(farmer, "Sunflower")
    over = farmer.post("/api/v1/pollination/bookings", json={"crop_cycle_id": sunflower, "provider_id": pid, "start_date": d(25),
                                                             "end_date": d(30), "colonies_requested": 20})
    assert over.status_code == 409


def test_reschedule_proposal_and_farmer_acceptance(other_farmer, provider):
    b = other_farmer.get("/api/v1/pollination/bookings").json()[0]
    prop = provider.post(f"/api/v1/pollination/bookings/{b['id']}/transition", json={
        "to": "reschedule_proposed", "version": b["version"], "start_date": d(18), "end_date": d(34), "note": "Hives free from the 18th"})
    assert prop.status_code == 200
    p = prop.json()
    assert p["proposed_start_date"] == d(18)
    acc = other_farmer.post(f"/api/v1/pollination/bookings/{b['id']}/transition", json={"to": "accepted", "version": p["version"]})
    assert acc.status_code == 200
    assert acc.json()["start_date"] == d(18) and acc.json()["proposed_start_date"] is None


def test_overlapping_booking_for_same_cycle_rejected(farmer):
    sunflower = cycle_id(farmer, "Sunflower")
    deccan = next(p["id"] for p in farmer.get("/api/v1/pollination/providers").json() if p["display_name"] == "Deccan Pollination Services")
    pid = _madhuban_id(farmer)
    r = farmer.post("/api/v1/pollination/bookings", json={"crop_cycle_id": sunflower, "provider_id": pid, "start_date": d(10),
                                                         "end_date": d(15), "colonies_requested": 2})
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflicting_booking"
    assert deccan


def test_incompatible_provider_rejected(farmer):
    mustard = cycle_id(farmer, "Mustard")
    kullu = next(p["id"] for p in farmer.get("/api/v1/pollination/providers").json() if p["display_name"] == "Kullu Valley Beekeepers")
    r = farmer.post("/api/v1/pollination/bookings", json={"crop_cycle_id": mustard, "provider_id": kullu, "start_date": d(24),
                                                         "end_date": d(30), "colonies_requested": 2})
    assert r.status_code == 409 and r.json()["error"]["code"] == "provider_incompatible"


def test_booking_creation_is_idempotent(farmer):
    mustard = cycle_id(farmer, "Mustard")
    body = {"crop_cycle_id": mustard, "provider_id": _madhuban_id(farmer), "start_date": d(24), "end_date": d(30), "colonies_requested": 3}
    h = {"Idempotency-Key": "test-key-123"}
    a = farmer.post("/api/v1/pollination/bookings", json=body, headers=h)
    b = farmer.post("/api/v1/pollination/bookings", json=body, headers=h)
    assert a.status_code == 201 and b.status_code == 201 and a.json()["id"] == b.json()["id"]
    body["colonies_requested"] = 4
    c = farmer.post("/api/v1/pollination/bookings", json=body, headers=h)
    assert c.status_code == 409
    assert len([x for x in farmer.get("/api/v1/pollination/bookings").json() if x["cycle"]["id"] == mustard]) == 1


def test_provider_availability_rules(provider):
    prof = provider.get("/api/v1/pollination/profile").json()
    overlap = provider.post("/api/v1/pollination/availability", json={"start_date": d(10), "end_date": d(20), "colonies_available": 5})
    assert overlap.status_code == 409
    too_many = provider.post("/api/v1/pollination/availability", json={"start_date": d(100), "end_date": d(120), "colonies_available": 500})
    assert too_many.status_code == 422
    ok = provider.post("/api/v1/pollination/availability", json={"start_date": d(100), "end_date": d(120), "colonies_available": 50})
    assert ok.status_code == 201 and len(ok.json()["availability"]) == len(prof["availability"]) + 1
    # window with an accepted booking cannot be deleted
    seeded = prof["availability"][0]
    assert provider.delete(f"/api/v1/pollination/availability/{seeded['id']}").status_code == 409


def test_concurrent_accepts_cannot_overbook(db_seeded):
    """Two bookings that each fit alone but not together: accepting both at once leaves exactly one accepted."""
    import os
    import threading

    import pytest

    if not os.environ.get("DATABASE_URL", "").startswith("postgresql"):
        pytest.skip("row-level locking is exercised on PostgreSQL only")
    farmer = Client().login("ramesh@agastya.demo")
    other = Client().login("sunita@agastya.demo")
    provider = Client().login("anil@agastya.demo")
    pid = _madhuban_id(farmer)
    mustard = cycle_id(farmer, "Mustard")
    a = farmer.post("/api/v1/pollination/bookings", json={"crop_cycle_id": mustard, "provider_id": pid, "start_date": d(24),
                                                         "end_date": d(30), "colonies_requested": 41}).json()
    theirs = other.get("/api/v1/pollination/bookings").json()[0]
    # Sunita's request is 6 colonies on days 15-32; bump it to 40 by rescheduling via the farmer flow
    r = other.post(f"/api/v1/pollination/bookings/{theirs['id']}/transition", json={"to": "requested", "version": theirs["version"], "start_date": d(24), "end_date": d(30)})
    assert r.status_code == 200
    from app.core.db import SessionLocal
    from app.modules.pollination.models import PollinationBooking

    with SessionLocal() as s:  # test setup: make the second request 41 colonies too: 41 + 41 > 80 available
        b = s.get(PollinationBooking, theirs["id"])
        b.colonies_requested = 41
        s.commit()
    bookings = provider.get("/api/v1/pollination/bookings?status=requested").json()
    results = []

    def go(b):
        results.append(provider.post(f"/api/v1/pollination/bookings/{b['id']}/transition", json={"to": "accepted", "version": b["version"]}).status_code)

    threads = [threading.Thread(target=go, args=(b,)) for b in bookings if b["id"] in (a["id"], theirs["id"])]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == [200, 409]
