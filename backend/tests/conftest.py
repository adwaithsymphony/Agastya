from __future__ import annotations

import os
import tempfile
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

_tmp = tempfile.mkdtemp(prefix="agastya-test-")
os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["LOCAL_STORAGE_DIR"] = os.path.join(_tmp, "uploads")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{os.path.join(_tmp, 'test.db')}")
os.environ["DEMO_MODE"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

import app.models  # noqa: E402,F401
from app.core import clock  # noqa: E402
from app.core.db import Base, SessionLocal, get_engine  # noqa: E402
from app.core.security import CSRF_COOKIE  # noqa: E402
from app.main import app as asgi_app  # noqa: E402
from app.ml.crop_vision import get_model  # noqa: E402

TZ = ZoneInfo("Asia/Kolkata")
TODAY = date.today()


@pytest.fixture(scope="session", autouse=True)
def _model_loaded():
    get_model().load()


@pytest.fixture()
def db_seeded():
    """Fresh schema + demonstration data for each test, with time frozen at 11:00 IST."""
    from app.seed import seed

    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    seed(TODAY)
    clock.freeze(datetime.combine(TODAY, time(11, 0), tzinfo=TZ))
    yield
    clock.freeze(None)


class Client:
    """TestClient wrapper that sends the CSRF header like the real frontend."""

    def __init__(self):
        self.c = TestClient(asgi_app)

    def login(self, email: str, password: str = "agastya-demo"):
        r = self.c.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return self

    def _h(self, headers=None):
        h = dict(headers or {})
        tok = self.c.cookies.get(CSRF_COOKIE)
        if tok:
            h["X-CSRF-Token"] = tok
        return h

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, headers=None, **kw):
        return self.c.post(url, headers=self._h(headers), **kw)

    def put(self, url, headers=None, **kw):
        return self.c.put(url, headers=self._h(headers), **kw)

    def patch(self, url, headers=None, **kw):
        return self.c.patch(url, headers=self._h(headers), **kw)

    def delete(self, url, headers=None, **kw):
        return self.c.delete(url, headers=self._h(headers), **kw)


@pytest.fixture()
def client(db_seeded):
    return Client


@pytest.fixture()
def farmer(db_seeded):
    return Client().login("ramesh@agastya.demo")


@pytest.fixture()
def other_farmer(db_seeded):
    return Client().login("sunita@agastya.demo")


@pytest.fixture()
def provider(db_seeded):
    return Client().login("anil@agastya.demo")


@pytest.fixture()
def buyer(db_seeded):
    return Client().login("imran@agastya.demo")


@pytest.fixture()
def reviewer(db_seeded):
    return Client().login("asha@agastya.demo")


@pytest.fixture()
def admin(db_seeded):
    return Client().login("admin@agastya.demo")


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.close()


def cycle_id(client: Client, crop_name: str) -> int:
    for c in client.get("/api/v1/crop-cycles").json():
        if c["crop"]["name"] == crop_name and c["status"] != "closed":
            return c["id"]
    raise AssertionError(f"no cycle for {crop_name}")
