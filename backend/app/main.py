from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.csrf import CSRFMiddleware
from app.core.errors import install_error_handlers
from app.ml.crop_vision import get_model
from app.modules.admin.router import router as admin_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.farms.router import router as farms_router
from app.modules.identity.router import router as auth_router
from app.modules.monitoring.router import router as monitoring_router
from app.modules.notifications.router import router as notifications_router
from app.modules.pesticide.router import router as pesticide_router
from app.modules.pollination.router import router as pollination_router
from app.modules.produce.router import router as produce_router
from app.modules.plant_intelligence.router import router as plant_intelligence_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_model().load()  # failure is reported through /model-predictions/status, never faked
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="AGASTYA API",
        version="1.0.0",
        description="AI-Powered Crop Lifecycle Intelligence — pollination, crop monitoring, pesticide safety and produce rerouting.",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    install_error_handlers(app)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"],
    )

    api = APIRouter(prefix="/api/v1")
    for r in (
        auth_router,
        farms_router,
        monitoring_router,
        pesticide_router,
        pollination_router,
        produce_router,
        notifications_router,
        dashboard_router,
        admin_router,
        plant_intelligence_router,
    ):
        api.include_router(r)
    app.include_router(api)

    @app.get("/api/health", tags=["system"])
    def health():
        # Public readiness probe. It reports only whether the database is reachable and migrated;
        # table names, account counts and driver errors stay in server logs, `python -m app.doctor`
        # and the administrator health page.
        from app.core.db import database_status

        db_state = database_status()
        ready = db_state["available"] and db_state["schema_ready"]
        body = {
            "status": "ok" if ready else "degraded",
            "database": {"available": db_state["available"], "schema_ready": db_state["schema_ready"]},
            "model_available": get_model().available,
        }
        if not get_settings().is_production:
            body["setup_hints"] = True  # lets the sign-in page show local setup steps in development only
        return body

    _mount_portal(app)
    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    """Optionally serve the built frontend (FRONTEND_DIST) from the same origin, e.g. for a single-process demo."""
    import os
    from pathlib import Path

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    dist = os.getenv("FRONTEND_DIST")
    if not dist or not (Path(dist) / "index.html").exists():
        return
    root = Path(dist).resolve()
    app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            from app.core.errors import NotFound

            raise NotFound("Not found.")
        candidate = (root / path).resolve()
        if path and root in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(root / "index.html")




def _mount_portal(app: FastAPI) -> None:
    """Serve an independently buildable Plant Intelligence SPA when PORTAL_DIST is configured."""
    import os
    from pathlib import Path
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    dist = os.getenv("PORTAL_DIST")
    if not dist or not (Path(dist) / "index.html").exists():
        return
    root = Path(dist).resolve()
    app.mount("/plant-portal/assets", StaticFiles(directory=root / "assets"), name="plant-portal-assets")

    @app.get("/plant-portal", include_in_schema=False)
    @app.get("/plant-portal/{path:path}", include_in_schema=False)
    def plant_portal_spa(path: str = ""):
        candidate = (root / path).resolve()
        if path and root in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(root / "index.html")

app = create_app()
