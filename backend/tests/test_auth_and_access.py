from tests.conftest import Client, cycle_id


def test_login_me_logout(db_seeded):
    c = Client().login("ramesh@agastya.demo")
    me = c.get("/api/v1/auth/me").json()
    assert me["role"] == "farmer" and me["organization_name"] == "Patil Family Farms"
    assert c.post("/api/v1/auth/logout").status_code == 204
    assert c.get("/api/v1/auth/me").status_code == 401


def test_bad_password_rejected_without_detail(db_seeded):
    r = Client().c.post("/api/v1/auth/login", json={"email": "ramesh@agastya.demo", "password": "wrong"})
    assert r.status_code == 401
    assert r.json()["error"]["message"] == "Email or password is incorrect."
    r = Client().c.post("/api/v1/auth/login", json={"email": "nobody@agastya.demo", "password": "wrong"})
    assert r.status_code == 401


def test_unauthenticated_requests_rejected(db_seeded):
    c = Client()
    for url in ["/api/v1/farms", "/api/v1/dashboard", "/api/v1/crop-cycles", "/api/v1/batches"]:
        assert c.get(url).status_code == 401


def test_csrf_required_for_state_changes(farmer):
    r = farmer.c.post("/api/v1/farms", json={"name": "X Farm", "district": "Pune", "state": "Maharashtra"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    r = farmer.post("/api/v1/farms", json={"name": "X Farm", "district": "Pune", "state": "Maharashtra"})
    assert r.status_code == 201


def test_no_public_account_listing(db_seeded):
    # Sample credentials are never exposed through the API or the sign-in page.
    assert Client().get("/api/v1/auth/demo-accounts").status_code in (404, 405)


def test_login_email_is_case_insensitive(db_seeded):
    Client().login("Ramesh@Agastya.DEMO")


def test_deactivated_account_gets_clear_message_only_with_correct_password(admin):
    users = admin.get("/api/v1/admin/users?q=farah").json()["items"]
    admin.patch(f"/api/v1/admin/users/{users[0]['id']}", json={"is_active": False})
    wrong = Client().c.post("/api/v1/auth/login", json={"email": "farah@agastya.demo", "password": "nope"})
    assert wrong.status_code == 401 and wrong.json()["error"]["message"] == "Email or password is incorrect."
    right = Client().c.post("/api/v1/auth/login", json={"email": "farah@agastya.demo", "password": "agastya-demo"})
    assert right.status_code == 403 and right.json()["error"]["code"] == "account_disabled"


def test_expired_and_tampered_sessions_are_rejected(db_seeded):
    from datetime import datetime, timedelta, timezone

    import jwt

    from app.core.config import get_settings
    from app.core.security import SESSION_COOKIE

    c = Client().login("ramesh@agastya.demo")
    token = c.c.cookies.get(SESSION_COOKIE)
    claims = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    expired = jwt.encode({**claims, "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}, get_settings().secret_key, algorithm="HS256")
    c.c.cookies.set(SESSION_COOKIE, expired)
    assert c.get("/api/v1/auth/me").status_code == 401
    forged = jwt.encode({**claims, "sub": "1"}, "not-the-secret", algorithm="HS256")
    c.c.cookies.set(SESSION_COOKIE, forged)
    assert c.get("/api/v1/auth/me").status_code == 401
    unsigned = jwt.encode(dict(claims), None, algorithm="none")
    c.c.cookies.set(SESSION_COOKIE, unsigned)
    assert c.get("/api/v1/auth/me").status_code == 401


def test_login_validation_errors_are_422_not_500(db_seeded):
    r = Client().c.post("/api/v1/auth/login", json={"email": "", "password": ""})
    assert r.status_code == 422
    r = Client().c.post("/api/v1/auth/login", content=b"not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_passwords_are_never_logged(db_seeded, caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    Client().c.post("/api/v1/auth/login", json={"email": "ramesh@agastya.demo", "password": "wrong-secret-123"})
    Client().login("ramesh@agastya.demo")
    assert "wrong-secret-123" not in caplog.text and "agastya-demo" not in caplog.text


def test_cross_organisation_access_is_rejected(farmer, other_farmer):
    tomato = cycle_id(farmer, "Tomato")
    assert other_farmer.get(f"/api/v1/crop-cycles/{tomato}").status_code == 404
    assert other_farmer.get(f"/api/v1/harvest-assessments/{tomato}").status_code == 404
    assert other_farmer.get(f"/api/v1/crop-cycles/{tomato}/timeline").status_code == 404
    batches = farmer.get("/api/v1/batches").json()
    assert other_farmer.get(f"/api/v1/batches/{batches[0]['id']}").status_code == 404
    r = other_farmer.post("/api/v1/applications", json={
        "crop_cycle_id": tomato, "product_id": 1, "applied_at": "2026-01-01T08:00:00+05:30", "dose_value": 1, "dose_unit": "g/L"})
    assert r.status_code == 404
    farm_ids = [f["id"] for f in farmer.get("/api/v1/farms").json()]
    assert not set(farm_ids) & {f["id"] for f in other_farmer.get("/api/v1/farms").json()}


def test_role_restrictions_enforced_by_backend(provider, buyer, reviewer, farmer):
    assert provider.get("/api/v1/applications").status_code == 403
    assert buyer.get("/api/v1/crop-cycles").status_code == 403
    assert buyer.get("/api/v1/batches").status_code == 403
    assert farmer.get("/api/v1/admin/users").status_code == 403
    assert farmer.post("/api/v1/pesticide-labels/1/verify", json={
        "source_reference": "x" * 5, "phi_days": 1, "valid_from": "2025-01-01"}).status_code == 403
    assert reviewer.get("/api/v1/batches").status_code == 403
    assert provider.get("/api/v1/reviews/queue").status_code == 403
    assert farmer.get("/api/v1/pollination/profile").status_code == 403


def test_reviewer_can_read_but_not_write_observations(reviewer, farmer):
    obs = farmer.get("/api/v1/observations").json()["items"][0]
    assert reviewer.get(f"/api/v1/observations/{obs['id']}").status_code == 200
    assert reviewer.get(f"/api/v1/observations/{obs['id']}/image").status_code == 200
    r = reviewer.post(f"/api/v1/observations/{obs['id']}/reanalyze")
    assert r.status_code == 403


def test_role_change_invalidates_existing_session(admin, buyer):
    uid = buyer.get("/api/v1/auth/me").json()["id"]
    r = admin.patch(f"/api/v1/admin/users/{uid}", json={"role": "farmer"})
    assert r.status_code == 200
    assert buyer.get("/api/v1/auth/me").status_code == 401
    events = admin.get("/api/v1/admin/audit?entity_type=user").json()["items"]
    assert any(e["action"] == "user.access_changed" for e in events)


def test_admin_cannot_remove_own_access(admin):
    me = admin.get("/api/v1/auth/me").json()
    assert admin.patch(f"/api/v1/admin/users/{me['id']}", json={"is_active": False}).status_code == 409


def test_password_change(farmer):
    r = farmer.post("/api/v1/auth/password", json={"current_password": "agastya-demo", "new_password": "a-much-longer-password"})
    assert r.status_code == 204
    assert farmer.get("/api/v1/auth/me").status_code == 200  # new cookie issued
    Client().login("ramesh@agastya.demo", "a-much-longer-password")
