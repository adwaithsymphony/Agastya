"""Dashboards, notifications, farms/cycles workflows, admin and migrations."""
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from tests.conftest import TODAY, Client, cycle_id


def test_dashboards_for_every_role(farmer, provider, buyer, reviewer, admin):
    f = farmer.get("/api/v1/dashboard").json()
    assert f["role"] == "farmer"
    m = f["metrics"]
    assert m["active_cycles"] == 4 and m["batches_needing_destination"] == 2
    assert m["rerouted_delivered_kg"] == 400.0
    assert any(a["kind"] == "batch_destination" for a in f["attention"])
    assert any(a["kind"] == "flowering_unbooked" for a in f["attention"])
    p = provider.get("/api/v1/dashboard").json()
    assert p["metrics"]["incoming_requests"] == 1 and p["metrics"]["upcoming_services"] == 1
    b = buyer.get("/api/v1/dashboard").json()
    assert b["metrics"]["active_deliveries"] == 1
    r = reviewer.get("/api/v1/dashboard").json()
    assert r["metrics"]["awaiting_review"] >= 1 and r["metrics"]["uncertain"] >= 1
    a = admin.get("/api/v1/dashboard").json()
    assert a["model"]["available"] is True and a["metrics"]["unverified_labels"] == 1


def test_notifications_read_state(farmer):
    page = farmer.get("/api/v1/notifications").json()
    assert page["unread_count"] >= 1
    nid = page["items"][0]["id"]
    assert farmer.post(f"/api/v1/notifications/{nid}/read").json()["read_at"] is not None
    farmer.post("/api/v1/notifications/read-all")
    assert farmer.get("/api/v1/notifications").json()["unread_count"] == 0


def test_cannot_read_other_users_notification(farmer, buyer):
    nid = farmer.get("/api/v1/notifications").json()["items"][0]["id"]
    assert buyer.post(f"/api/v1/notifications/{nid}/read").status_code == 404


def test_farm_field_cycle_workflow(farmer):
    farm = farmer.post("/api/v1/farms", json={"name": "Niphad Farm", "district": "Nashik", "state": "Maharashtra"}).json()
    field = farmer.post(f"/api/v1/farms/{farm['id']}/fields", json={"name": "Plot A", "area_ha": 0.8}).json()
    assert farmer.post(f"/api/v1/farms/{farm['id']}/fields", json={"name": "plot a", "area_ha": 1}).status_code == 409
    assert farmer.post(f"/api/v1/farms/{farm['id']}/fields", json={"name": "Plot B", "area_ha": 0}).status_code == 422
    crops = {c["code"]: c["id"] for c in farmer.get("/api/v1/crops").json()}
    bad = farmer.post("/api/v1/crop-cycles", json={"field_id": field["id"], "crop_id": crops["cucumber"], "sowing_date": str(TODAY),
                                                   "expected_flowering_start": str(TODAY + timedelta(days=40)),
                                                   "expected_flowering_end": str(TODAY + timedelta(days=30))})
    assert bad.status_code == 422
    c = farmer.post("/api/v1/crop-cycles", json={"field_id": field["id"], "crop_id": crops["cucumber"], "sowing_date": str(TODAY),
                                                 "expected_flowering_start": str(TODAY + timedelta(days=30)),
                                                 "expected_flowering_end": str(TODAY + timedelta(days=45)), "current_stage": "Sowing"})
    assert c.status_code == 201, c.text
    cid = c.json()["id"]
    dup = farmer.post("/api/v1/crop-cycles", json={"field_id": field["id"], "crop_id": crops["cucumber"], "sowing_date": str(TODAY)})
    assert dup.status_code == 409
    s = farmer.post(f"/api/v1/crop-cycles/{cid}/stages", json={"stage": "Vegetative", "observed_on": str(TODAY)})
    assert s.status_code == 201
    assert farmer.post(f"/api/v1/crop-cycles/{cid}/stages", json={"stage": "Bloom", "observed_on": str(TODAY)}).status_code == 422
    assert farmer.get(f"/api/v1/crop-cycles/{cid}").json()["current_stage"] == "Vegetative"
    t = farmer.patch(f"/api/v1/crop-cycles/{cid}", json={"status": "closed"})
    assert t.status_code == 200
    assert farmer.patch(f"/api/v1/crop-cycles/{cid}", json={"status": "active"}).status_code == 409


def test_admin_model_and_health(admin):
    m = admin.get("/api/v1/admin/models").json()
    assert m["runtime"]["available"] and m["registry"][0]["key"] == "crop-vision-plantvillage"
    assert m["card"]["metrics"]["test_accuracy"] > 0.9
    h = admin.get("/api/v1/admin/health").json()
    assert h["database"] and h["storage"]


def test_alembic_migrations_apply_cleanly(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'mig.db'}"}
    up = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend, env=env, capture_output=True, text=True)
    assert up.returncode == 0, up.stderr
    down = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "base"], cwd=backend, env=env, capture_output=True, text=True)
    assert down.returncode == 0, down.stderr
