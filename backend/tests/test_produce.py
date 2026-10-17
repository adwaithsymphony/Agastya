from datetime import timedelta

from tests.conftest import TODAY, Client, cycle_id


def batch_by_code(farmer, code):
    return next(b for b in farmer.get("/api/v1/batches").json() if b["code"] == code)


def test_reroute_after_buyer_cancellation_full_flow(farmer):
    b = batch_by_code(farmer, "TOM-A2")
    assert b["status"] == "needs_destination"
    run = farmer.post(f"/api/v1/batches/{b['id']}/buyer-matches", json={"trigger": "buyer_cancelled"}).json()
    eligible = [m for m in run["matches"] if m["eligible"]]
    excluded = {m["buyer"]["display_name"]: m["exclusions"] for m in run["matches"] if not m["eligible"]}
    assert [m["rank"] for m in eligible] == list(range(1, len(eligible) + 1))
    assert all(m["score"] is not None and m["reasons"] for m in eligible)
    assert "Buyer being replaced" in excluded["Pune Greens Retail"]
    assert any("grade" in e for e in excluded["Western Ghats Agro Processors"])
    top = eligible[0]
    assert top["components"].keys() == {"timing", "distance", "fit", "grade"}

    detail = farmer.get(f"/api/v1/batches/{b['id']}").json()
    r = farmer.post(f"/api/v1/batches/{b['id']}/destination", json={"match_id": top["id"], "version": detail["version"]},
                    headers={"Idempotency-Key": "confirm-1"})
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["status"] == "assigned"
    assert after["current_assignment"]["buyer"]["display_name"] == top["buyer"]["display_name"]
    assert after["current_assignment"]["reason"] == "reroute_buyer_cancelled"
    assert after["current_assignment"]["shipment"]["status"] == "scheduled"
    statuses = [a["status"] for a in after["assignments"]]
    assert statuses.count("active") == 1 and "cancelled_by_buyer" in statuses  # history retained
    # retry with the same key returns the same result, no duplicate assignment
    again = farmer.post(f"/api/v1/batches/{b['id']}/destination", json={"match_id": top["id"], "version": detail["version"]},
                        headers={"Idempotency-Key": "confirm-1"})
    assert again.status_code == 200 and len(again.json()["assignments"]) == len(after["assignments"])
    # persisted after reload
    assert farmer.get(f"/api/v1/batches/{b['id']}").json()["status"] == "assigned"


def test_stale_version_and_stale_recommendations_rejected(farmer):
    b = batch_by_code(farmer, "TOM-A2")
    run1 = farmer.post(f"/api/v1/batches/{b['id']}/buyer-matches", json={"trigger": "buyer_cancelled"}).json()
    run2 = farmer.post(f"/api/v1/batches/{b['id']}/buyer-matches", json={"trigger": "buyer_cancelled"}).json()
    v = farmer.get(f"/api/v1/batches/{b['id']}").json()["version"]
    old = next(m for m in run1["matches"] if m["eligible"])
    r = farmer.post(f"/api/v1/batches/{b['id']}/destination", json={"match_id": old["id"], "version": v})
    assert r.status_code == 409 and r.json()["error"]["code"] == "stale_recommendations"
    new = next(m for m in run2["matches"] if m["eligible"])
    r = farmer.post(f"/api/v1/batches/{b['id']}/destination", json={"match_id": new["id"], "version": v - 1})
    assert r.status_code == 409 and r.json()["error"]["code"] == "stale_version"
    ineligible = next(m for m in run2["matches"] if not m["eligible"])
    r = farmer.post(f"/api/v1/batches/{b['id']}/destination", json={"match_id": ineligible["id"], "version": v})
    assert r.status_code == 422


def test_buyer_cancellation_triggers_needs_destination_and_notifies(farmer, buyer):
    deliveries = buyer.get("/api/v1/buyers/me/deliveries").json()
    active = next(d for d in deliveries if d["status"] == "active")
    assert buyer.post(f"/api/v1/buyers/me/deliveries/{active['id']}/cancel", json={"reason": "x"}).status_code == 422
    r = buyer.post(f"/api/v1/buyers/me/deliveries/{active['id']}/cancel", json={"reason": "Market yard closed"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled_by_buyer"
    assert r.json()["shipment"]["status"] == "cancelled"
    b = farmer.get(f"/api/v1/batches/{active['batch']['id']}").json()
    assert b["status"] == "needs_destination" and b["current_assignment"] is None
    notes = farmer.get("/api/v1/notifications?unread=true").json()["items"]
    assert any(n["event_type"] == "batch.buyer_cancelled" and n["entity_id"] == b["id"] for n in notes)
    # cancelling twice is rejected
    assert buyer.post(f"/api/v1/buyers/me/deliveries/{active['id']}/cancel", json={"reason": "again"}).status_code == 409


def test_other_buyer_cannot_cancel(db_seeded):
    other = Client().login("farah@agastya.demo")
    imran = Client().login("imran@agastya.demo")
    aid = imran.get("/api/v1/buyers/me/deliveries").json()[0]["id"]
    assert other.post(f"/api/v1/buyers/me/deliveries/{aid}/cancel", json={"reason": "not mine"}).status_code == 404


def test_over_allocation_prevented(farmer):
    """Two batches compete for Annapoorna's 1,500 kg demand; the second confirmation is refused."""
    tomato = cycle_id(farmer, "Tomato")
    harvested = str(TODAY - timedelta(days=2))
    ids = []
    for qty in ("900", "800"):
        r = farmer.post("/api/v1/batches", json={"crop_cycle_id": tomato, "quantity_value": qty, "unit": "kg", "grade": "C",
                                                 "harvested_on": harvested, "shelf_life_days": 5})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    runs = [farmer.post(f"/api/v1/batches/{i}/buyer-matches", json={"trigger": "unassigned"}).json() for i in ids]
    picks = [next(m for m in run["matches"] if m["eligible"] and m["buyer"]["display_name"] == "Annapoorna Community Kitchen")
             for run in runs]
    v0 = farmer.get(f"/api/v1/batches/{ids[0]}").json()["version"]
    v1 = farmer.get(f"/api/v1/batches/{ids[1]}").json()["version"]
    assert farmer.post(f"/api/v1/batches/{ids[0]}/destination", json={"match_id": picks[0]["id"], "version": v0}).status_code == 200
    r = farmer.post(f"/api/v1/batches/{ids[1]}/destination", json={"match_id": picks[1]["id"], "version": v1})
    assert r.status_code == 409 and r.json()["error"]["code"] == "no_longer_eligible"


def test_disruption_reroute_supersedes_active_assignment(farmer):
    b = batch_by_code(farmer, "TOM-A1")
    assert farmer.post(f"/api/v1/batches/{b['id']}/buyer-matches", json={"trigger": "disruption"}).status_code == 422
    run = farmer.post(f"/api/v1/batches/{b['id']}/buyer-matches", json={"trigger": "disruption", "note": "Highway closed near Sinnar"}).json()
    names = {m["buyer"]["display_name"]: m for m in run["matches"]}
    assert not names["Godavari Fresh Traders"]["eligible"]  # current buyer excluded
    pick = next(m for m in run["matches"] if m["eligible"])
    v = farmer.get(f"/api/v1/batches/{b['id']}").json()["version"]
    after = farmer.post(f"/api/v1/batches/{b['id']}/destination", json={"match_id": pick["id"], "version": v}).json()
    statuses = {a["buyer"]["display_name"]: a["status"] for a in after["assignments"]}
    assert statuses["Godavari Fresh Traders"] == "superseded"
    assert after["current_assignment"]["reason"] == "reroute_disruption"


def test_shipment_dispatch_and_delivery(farmer, buyer):
    b = batch_by_code(farmer, "TOM-A1")
    sh = b["current_assignment"]["shipment"]
    assert buyer.post(f"/api/v1/shipments/{sh['id']}/status", json={"to": "dispatched"}).status_code == 409
    assert farmer.post(f"/api/v1/shipments/{sh['id']}/status", json={"to": "dispatched"}).status_code == 200
    assert farmer.get(f"/api/v1/batches/{b['id']}").json()["status"] == "in_transit"
    assert farmer.post(f"/api/v1/shipments/{sh['id']}/status", json={"to": "delivered"}).status_code == 409
    assert buyer.post(f"/api/v1/shipments/{sh['id']}/status", json={"to": "delivered", "note": "OK"}).status_code == 200
    final = farmer.get(f"/api/v1/batches/{b['id']}").json()
    assert final["status"] == "delivered" and final["assignments"][0]["status"] == "completed"


def test_batch_validation(farmer):
    tomato = cycle_id(farmer, "Tomato")
    base = {"crop_cycle_id": tomato, "quantity_value": "10", "unit": "kg", "grade": "A", "harvested_on": str(TODAY - timedelta(days=3))}
    assert farmer.post("/api/v1/batches", json={**base, "quantity_value": "-5"}).status_code == 422
    assert farmer.post("/api/v1/batches", json={**base, "grade": "Z"}).status_code == 422
    assert farmer.post("/api/v1/batches", json={**base, "unit": "bag"}).status_code == 422
    assert farmer.post("/api/v1/batches", json={**base, "harvested_on": str(TODAY + timedelta(days=1))}).status_code == 422


def test_buyer_demand_and_matching_produce(buyer):
    crops = {c["name"]: c["id"] for c in buyer.get("/api/v1/crops").json()}
    r = buyer.post("/api/v1/buyer-demands", json={
        "crop_id": crops["Capsicum"], "accepted_grades": ["B", "A"], "quantity_kg": "300",
        "valid_from": str(TODAY), "valid_until": str(TODAY + timedelta(days=10)),
        "delivery_start": str(TODAY), "delivery_end": str(TODAY + timedelta(days=5))})
    assert r.status_code == 201 and r.json()["accepted_grades"] == ["A", "B"]
    matching = buyer.get("/api/v1/buyers/me/matching-produce").json()
    assert any(m["crop"] == "Capsicum" for m in matching)
    assert all("farm" not in m for m in matching)  # farm identity not exposed


def test_concurrent_confirmations_assign_only_once(farmer):
    """Two simultaneous confirmations for the same batch: exactly one succeeds (row lock + version check)."""
    import os
    import threading

    import pytest

    if not os.environ.get("DATABASE_URL", "").startswith("postgresql"):
        pytest.skip("row-level locking is exercised on PostgreSQL only")
    b = batch_by_code(farmer, "TOM-A2")
    run = farmer.post(f"/api/v1/batches/{b['id']}/buyer-matches", json={"trigger": "buyer_cancelled"}).json()
    eligible = [m for m in run["matches"] if m["eligible"]][:2]
    v = farmer.get(f"/api/v1/batches/{b['id']}").json()["version"]
    results = []

    def go(match_id):
        results.append(farmer.post(f"/api/v1/batches/{b['id']}/destination", json={"match_id": match_id, "version": v}).status_code)

    threads = [threading.Thread(target=go, args=(m["id"],)) for m in (eligible * 2)[:2]]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == [200, 409]
    final = farmer.get(f"/api/v1/batches/{b['id']}").json()
    assert [a["status"] for a in final["assignments"]].count("active") == 1
