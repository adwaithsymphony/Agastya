"""Read-only local setup diagnostics for AGASTYA. Run: python -m app.doctor"""
from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version

import app.models  # noqa: F401 - register the full schema
from sqlalchemy import inspect, select, func

from app.core.config import get_settings
from app.core.db import Base, get_engine
from app.ml.crop_vision import get_model
from app.modules.identity.models import User


REQUIRED_PACKAGES = ("fastapi", "uvicorn", "sqlalchemy", "alembic", "psycopg", "PyJWT", "onnxruntime", "numpy", "pillow", "tzdata")


def main() -> int:
    failed = False
    print("AGASTYA setup doctor (read-only; does not reset or modify records)\n")
    print(f"Python: {sys.version.split()[0]} (supported: 3.11–3.13)")
    if sys.version_info < (3, 11) or sys.version_info >= (3, 14):
        print("  FAIL: use Python 3.11, 3.12, or 3.13")
        failed = True
    for package in REQUIRED_PACKAGES:
        try:
            print(f"Dependency {package}: {version(package)}")
        except PackageNotFoundError:
            print(f"  FAIL: missing {package}; install backend/requirements-dev.txt")
            failed = True

    try:
        from zoneinfo import ZoneInfo

        ZoneInfo("Asia/Kolkata")
        print("Time-zone data: available")
    except Exception:
        print("  FAIL: time-zone data missing (common on Windows); run `pip install tzdata`")
        failed = True

    settings = get_settings()
    print(f"Environment: {settings.app_env}; demo mode enabled: {settings.demo_enabled}")
    try:
        engine = get_engine()
        inspector = inspect(engine)
        names = set(inspector.get_table_names())
        missing = sorted(set(Base.metadata.tables) - names)
        print(f"Database: connected ({engine.dialect.name})")
        if missing:
            print("  FAIL: missing schema tables: " + ", ".join(missing))
            print("  Fix: from backend folder run `alembic upgrade head`")
            failed = True
        else:
            print(f"Schema: ready ({len(names)} tables)")
        if "users" in names:
            with engine.connect() as conn:
                count = conn.execute(select(func.count()).select_from(User)).scalar_one()
                demos = conn.execute(select(func.count()).select_from(User).where(User.is_demo.is_(True))).scalar_one()
            print(f"Users: {count} total; {demos} sample accounts")
            if settings.demo_enabled and demos == 0:
                print("  ACTION: no sample users found; run `python -m app.seed` only if this database is intended for sample data")
        else:
            failed = True
    except Exception as exc:
        print(f"  FAIL: database check failed ({type(exc).__name__}): {exc}")
        print("  Check DATABASE_URL in the root .env and confirm PostgreSQL is running, or configure a local SQLite URL.")
        failed = True

    try:
        model = get_model().status()
        print(f"Crop model: {'available' if model['available'] else 'unavailable'}; version={model['version']}; error={model['error']}")
        if not model["available"]:
            print("  ACTION: verify onnxruntime is installed and backend/ml_models/crop_vision contains model.onnx and model_card.json")
            failed = True
    except Exception as exc:
        print(f"  FAIL: model check failed ({type(exc).__name__})")
        failed = True

    print("\nResult: " + ("CHECK FAILED — resolve the items above." if failed else "core setup checks passed."))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
