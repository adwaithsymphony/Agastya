"""Application settings, read from environment variables (optionally via a .env file)."""
from __future__ import annotations

import os
import secrets
import warnings
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

try:  # python-dotenv is optional at runtime
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:  # pragma: no cover
    pass

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: str) -> list[str]:
    return [s.strip() for s in os.getenv(name, default).split(",") if s.strip()]


@dataclass(frozen=True)
class Settings:
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", "postgresql+psycopg://agastya:agastya@localhost:5432/agastya"
        )
    )
    secret_key: str = field(default_factory=lambda: os.getenv("SECRET_KEY", ""))
    session_ttl_minutes: int = field(default_factory=lambda: int(os.getenv("SESSION_TTL_MINUTES", "720")))
    cookie_secure: bool = field(default_factory=lambda: _bool("COOKIE_SECURE", False))
    cors_origins: list[str] = field(default_factory=lambda: _list("CORS_ORIGINS", "http://localhost:5173,http://localhost:5174"))

    storage_backend: str = field(default_factory=lambda: os.getenv("STORAGE_BACKEND", "local"))
    local_storage_dir: str = field(
        default_factory=lambda: os.getenv("LOCAL_STORAGE_DIR", str(BACKEND_DIR / "var" / "uploads"))
    )
    s3_bucket: str = field(default_factory=lambda: os.getenv("S3_BUCKET", ""))
    s3_endpoint_url: str = field(default_factory=lambda: os.getenv("S3_ENDPOINT_URL", ""))
    s3_region: str = field(default_factory=lambda: os.getenv("S3_REGION", ""))
    max_upload_mb: int = field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_MB", "8")))
    image_retention_days: int = field(default_factory=lambda: int(os.getenv("IMAGE_RETENTION_DAYS", "730")))

    model_dir: str = field(
        default_factory=lambda: os.getenv("MODEL_DIR", str(BACKEND_DIR / "ml_models" / "crop_vision"))
    )
    uncertainty_threshold: float = field(
        default_factory=lambda: float(os.getenv("UNCERTAINTY_THRESHOLD", "0.70"))
    )

    demo_mode: bool = field(default_factory=lambda: _bool("DEMO_MODE", True))
    demo_date: str = field(default_factory=lambda: os.getenv("DEMO_DATE", ""))
    default_timezone: str = field(default_factory=lambda: os.getenv("DEFAULT_TIMEZONE", "Asia/Kolkata"))
    harvest_upcoming_window_days: int = field(
        default_factory=lambda: int(os.getenv("HARVEST_UPCOMING_WINDOW_DAYS", "3"))
    )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def demo_enabled(self) -> bool:
        """Demo helpers (seed credentials on the login screen) never run in production."""
        return self.demo_mode and not self.is_production

    def demo_today(self) -> date | None:
        return date.fromisoformat(self.demo_date) if self.demo_date else None


_ephemeral_key = secrets.token_urlsafe(48)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if not s.secret_key:
        if s.is_production:
            raise RuntimeError("SECRET_KEY must be set in production")
        warnings.warn("SECRET_KEY not set; using an ephemeral development key (sessions reset on restart)")
        s = Settings(secret_key=_ephemeral_key)
    if s.is_production and s.demo_mode:
        warnings.warn("DEMO_MODE is ignored in production")
    return s
