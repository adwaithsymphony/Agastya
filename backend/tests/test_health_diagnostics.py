from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.exc import ProgrammingError


def test_public_health_reports_readiness_without_internals(db_seeded):
    from app.main import app

    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == {"available": True, "schema_ready": True}
    # table names and account counts are not exposed to unauthenticated callers
    assert "missing_tables" not in body["database"] and "demo_accounts" not in body["database"]


def test_admin_health_has_schema_details(admin):
    h = admin.get("/api/v1/admin/health").json()
    assert h["schema_ready"] is True and h["missing_tables"] == [] and h["sample_accounts"] >= 1


def _broken_app():
    from fastapi import FastAPI

    from app.core.errors import install_error_handlers

    app = FastAPI()
    install_error_handlers(app)

    @app.get("/boom")
    def boom():
        raise ProgrammingError("SELECT 1", {}, Exception('relation "users" does not exist'))

    return app


def test_missing_schema_returns_503_with_dev_hint(db_seeded):
    r = TestClient(_broken_app(), raise_server_exceptions=False).get("/boom")
    assert r.status_code == 503
    err = r.json()["error"]
    assert err["code"] == "database_schema_error" and "alembic upgrade head" in err["message"]
    assert "users" not in err["message"]  # no raw driver text


def test_missing_schema_message_is_generic_in_production(db_seeded, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config, "get_settings", lambda: config.Settings(app_env="production", secret_key="x"))
    r = TestClient(_broken_app(), raise_server_exceptions=False).get("/boom")
    assert r.status_code == 503
    assert "alembic" not in r.json()["error"]["message"]


def test_login_on_unmigrated_database_is_503_not_500(db_seeded):
    """Regression for the original HTTP 500: login against a database without the schema."""
    from app.core.db import Base, get_engine
    from tests.conftest import Client

    Base.metadata.drop_all(get_engine())
    r = Client().c.post("/api/v1/auth/login", json={"email": "ramesh@agastya.demo", "password": "agastya-demo"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] in ("database_schema_error", "service_unavailable")
    health = Client().get("/api/health").json()
    assert health["status"] == "degraded" and health["database"]["schema_ready"] is False
