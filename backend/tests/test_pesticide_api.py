from datetime import datetime, time, timedelta

from tests.conftest import TODAY, TZ, cycle_id


def iso(days_ago: int, hh: int = 8) -> str:
    return datetime.combine(TODAY - timedelta(days=days_ago), time(hh), tzinfo=TZ).isoformat()


def product_id(client, name):
    return next(p["id"] for p in client.get("/api/v1/pesticide-products").json() if p["trade_name"] == name)


def test_seeded_statuses(farmer):
    overview = {o["cycle"]["crop"]: o["assessment"] for o in farmer.get("/api/v1/harvest-assessments").json()}
    tomato = overview["Tomato"]
    assert tomato["status"] == "restricted"
    assert tomato["earliest_eligible_date"] == str(TODAY + timedelta(days=4))
    cap = overview["Capsicum"]
    assert cap["status"] == "upcoming" and cap["unresolved_count"] == 1
    issue = [o for o in cap["outcomes"] if not o["resolved"]][0]
    assert issue["issue"] == "label_unverified" and issue["issue_message"]


def test_recording_application_recalculates_and_audits(farmer, admin):
    tomato = cycle_id(farmer, "Tomato")
    r = farmer.post("/api/v1/applications", json={
        "crop_cycle_id": tomato, "product_id": product_id(farmer, "Demo Spinosad 45 SC"), "applied_at": iso(0, 7),
        "dose_value": 0.3, "dose_unit": "ml per litre"})
    assert r.status_code == 201, r.text
    a = r.json()["assessment"]
    assert a["status"] == "restricted" and a["earliest_eligible_date"] == str(TODAY + timedelta(days=4))  # mancozeb still governs
    hist = farmer.get(f"/api/v1/harvest-assessments/{tomato}").json()
    assert len(hist["applications"]) == 4
    audit = admin.get("/api/v1/admin/audit?severity=safety").json()["items"]
    assert any(e["action"] == "application.recorded" for e in audit)


def test_application_without_label_is_unknown(farmer):
    sunflower = cycle_id(farmer, "Sunflower")
    r = farmer.post("/api/v1/applications", json={
        "crop_cycle_id": sunflower, "product_id": product_id(farmer, "Demo Copper Oxychloride 50 WP"),
        "applied_at": iso(20), "dose_value": 3, "dose_unit": "g per litre"})
    a = r.json()["assessment"]
    assert a["status"] == "unknown" and a["outcomes"][0]["issue"] == "no_label"


def test_future_or_naive_application_rejected(farmer):
    tomato = cycle_id(farmer, "Tomato")
    pid = product_id(farmer, "Demo Mancozeb 75 WP")
    future = (datetime.now(TZ) + timedelta(days=2)).isoformat()
    assert farmer.post("/api/v1/applications", json={"crop_cycle_id": tomato, "product_id": pid, "applied_at": future,
                                                     "dose_value": 1, "dose_unit": "g"}).status_code == 422
    assert farmer.post("/api/v1/applications", json={"crop_cycle_id": tomato, "product_id": pid, "applied_at": "2026-01-01T08:00:00",
                                                     "dose_value": 1, "dose_unit": "g"}).status_code == 422
    assert farmer.post("/api/v1/applications", json={"crop_cycle_id": tomato, "product_id": pid, "applied_at": iso(1),
                                                     "dose_value": -1, "dose_unit": "g"}).status_code == 422


def test_void_application_keeps_history_and_recomputes(farmer):
    tomato = cycle_id(farmer, "Tomato")
    detail = farmer.get(f"/api/v1/harvest-assessments/{tomato}").json()
    mancozeb = next(a for a in detail["applications"] if a["product"]["trade_name"] == "Demo Mancozeb 75 WP")
    assert farmer.post(f"/api/v1/applications/{mancozeb['id']}/void", json={"reason": "no"}).status_code == 422
    r = farmer.post(f"/api/v1/applications/{mancozeb['id']}/void", json={"reason": "Entered against the wrong field"})
    assert r.status_code == 200
    assert r.json()["assessment"]["status"] == "eligible"
    assert farmer.post(f"/api/v1/applications/{mancozeb['id']}/void", json={"reason": "again please"}).status_code == 409
    after = farmer.get(f"/api/v1/harvest-assessments/{tomato}").json()
    voided = next(a for a in after["applications"] if a["id"] == mancozeb["id"])
    assert voided["status"] == "voided" and voided["void_reason"]
    assert after["history"][0]["trigger"] == "application_voided"


def test_label_verification_resolves_unknown(farmer, admin):
    labels = admin.get("/api/v1/pesticide-labels?status=unverified").json()
    lbl = next(l for l in labels if l["crop"]["name"] == "Capsicum")
    r = admin.post(f"/api/v1/pesticide-labels/{lbl['id']}/verify", json={
        "source_reference": "Checked against approved label copy (test)", "phi_days": 3, "valid_from": "2025-01-01"})
    assert r.status_code == 200 and r.json()["cycles_recomputed"] >= 1
    cap = next(o for o in farmer.get("/api/v1/harvest-assessments").json() if o["cycle"]["crop"] == "Capsicum")
    assert cap["assessment"]["unresolved_count"] == 0
    assert admin.post(f"/api/v1/pesticide-labels/{lbl['id']}/verify", json={
        "source_reference": "again", "phi_days": 3, "valid_from": "2025-01-01"}).status_code == 409


def test_farmer_submitted_label_is_unverified_and_not_authoritative(farmer):
    sunflower = cycle_id(farmer, "Sunflower")
    pid = product_id(farmer, "Demo Copper Oxychloride 50 WP")
    crops = {c["name"]: c["id"] for c in farmer.get("/api/v1/crops").json()}
    farmer.post("/api/v1/applications", json={"crop_cycle_id": sunflower, "product_id": pid, "applied_at": iso(1),
                                              "dose_value": 3, "dose_unit": "g per litre"})
    r = farmer.post(f"/api/v1/pesticide-products/{pid}/labels", json={
        "crop_id": crops["Sunflower"], "label_version": "leaflet", "phi_days": 0, "source_reference": "Leaflet photo",
        "valid_from": "2025-01-01"})
    assert r.status_code == 201 and r.json()["verification_status"] == "unverified"
    a = next(o for o in farmer.get("/api/v1/harvest-assessments").json() if o["cycle"]["crop"] == "Sunflower")["assessment"]
    assert a["status"] == "unknown" and a["outcomes"][0]["issue"] == "label_unverified"


def test_batch_cannot_be_created_inside_phi(farmer):
    tomato = cycle_id(farmer, "Tomato")
    r = farmer.post("/api/v1/batches", json={"crop_cycle_id": tomato, "quantity_value": "500", "unit": "kg", "grade": "A",
                                             "harvested_on": str(TODAY)})
    assert r.status_code == 409 and r.json()["error"]["code"] == "harvest_restricted"
    ok = farmer.post("/api/v1/batches", json={"crop_cycle_id": tomato, "quantity_value": "5", "unit": "quintal", "grade": "B",
                                              "harvested_on": str(TODAY - timedelta(days=2)), "shelf_life_days": 6})
    assert ok.status_code == 201, ok.text
    assert ok.json()["quantity_kg"] == 500.0 and ok.json()["harvest_check_status"] == "eligible"


def test_seeded_rules_are_marked_fictional_everywhere(farmer, admin):
    tomato = cycle_id(farmer, "Tomato")
    a = farmer.get(f"/api/v1/harvest-assessments/{tomato}").json()["assessment"]
    assert a["uses_fictional_reference"] is True
    assert all(o["provenance"] == "fictional_sample" for o in a["outcomes"] if o["resolved"])
    labels = admin.get("/api/v1/pesticide-labels").json()
    seeded = [l for l in labels if l["source_kind"] == "demo_seed"]
    assert seeded and all(l["provenance"] == "fictional_sample" for l in seeded)
    # a farmer-submitted rule for a fictional sample product stays fictional even once verified
    sample_submitted = next(l for l in labels if l["source_kind"] == "manual")
    assert sample_submitted["provenance"] == "fictional_sample"
    r = admin.post(f"/api/v1/pesticide-labels/{sample_submitted['id']}/verify", json={
        "source_reference": "Approved label copy, page 2", "phi_days": 3, "valid_from": "2025-01-01"}).json()
    assert r["provenance"] == "fictional_sample"
    # a real (non-sample) product: "submitted" until verified, then "reference"
    p = farmer.post("/api/v1/pesticide-products", json={"trade_name": "Field Product X", "formulation": "EC"}).json()
    crops = {c["name"]: c["id"] for c in farmer.get("/api/v1/crops").json()}
    lbl = farmer.post(f"/api/v1/pesticide-products/{p['id']}/labels", json={
        "crop_id": crops["Tomato"], "label_version": "2026", "phi_days": 4, "source_reference": "Pack leaflet", "valid_from": "2026-01-01"}).json()
    assert lbl["provenance"] == "submitted"
    v = admin.post(f"/api/v1/pesticide-labels/{lbl['id']}/verify", json={
        "source_reference": "Registration certificate, label annex", "phi_days": 4, "valid_from": "2026-01-01"}).json()
    assert v["provenance"] == "reference"


def test_verification_revoke_is_controlled_and_audited(farmer, admin):
    labels = admin.get("/api/v1/pesticide-labels?status=verified").json()
    mancozeb_tomato = next(l for l in labels if l["product_name"] == "Demo Mancozeb 75 WP" and l["crop"]["name"] == "Tomato")
    assert farmer.post(f"/api/v1/pesticide-labels/{mancozeb_tomato['id']}/revoke", json={"reason": "test"}).status_code == 403
    assert admin.post(f"/api/v1/pesticide-labels/{mancozeb_tomato['id']}/revoke", json={"reason": "x"}).status_code == 422
    r = admin.post(f"/api/v1/pesticide-labels/{mancozeb_tomato['id']}/revoke", json={"reason": "Superseded label edition"})
    assert r.status_code == 200 and r.json()["verification_status"] == "unverified" and r.json()["cycles_recomputed"] >= 1
    # the restriction it set is no longer counted; the application becomes unresolved instead of eligible
    t = next(o for o in farmer.get("/api/v1/harvest-assessments").json() if o["cycle"]["crop"] == "Tomato")["assessment"]
    assert t["status"] == "unknown" and t["unresolved_count"] == 1
    assert admin.post(f"/api/v1/pesticide-labels/{mancozeb_tomato['id']}/revoke", json={"reason": "again please"}).status_code == 409
    events = admin.get("/api/v1/admin/audit?entity_type=product_label").json()["items"]
    assert any(e["action"] == "label.verification_revoked" for e in events)
