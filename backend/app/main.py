"""FastAPI application factory for AI YouTube Manager."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.services import action_executors  # noqa: F401  (registers approval executors)
from app.utils.errors import (
    AppError,
    app_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.utils.logging import get_logger
from app.utils.security import SecurityHeadersMiddleware

logger = get_logger("main")

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DIST_DIR = _PROJECT_ROOT / "frontend" / "dist"


def _register_routers(app: FastAPI) -> None:
    from app.routers import (  # noqa: PLC0415
        ai,
        analytics,
        autonomous,
        approvals,
        audit,
        auth,
        backup,
        bi,
        channels,
        comments,
        content_factory,
        content_plan,
        dashboard,
        health,
        learning,
        lifecycle,
        playlists,
        settings,
        videos,
        youtube,
    )

    api = app
    api.include_router(health.router, prefix="/api")
    api.include_router(auth.router, prefix="/api")
    api.include_router(youtube.router, prefix="/api")
    api.include_router(channels.router, prefix="/api")
    api.include_router(videos.router, prefix="/api")
    api.include_router(analytics.router, prefix="/api")
    api.include_router(comments.router, prefix="/api")
    api.include_router(playlists.router, prefix="/api")
    api.include_router(ai.router, prefix="/api")
    api.include_router(autonomous.router, prefix="/api")
    api.include_router(approvals.router, prefix="/api")
    api.include_router(audit.router, prefix="/api")
    api.include_router(dashboard.router, prefix="/api")
    api.include_router(content_plan.router, prefix="/api")
    api.include_router(content_factory.router, prefix="/api")
    api.include_router(settings.router, prefix="/api")
    api.include_router(backup.router, prefix="/api")
    api.include_router(bi.router, prefix="/api")
    api.include_router(lifecycle.router, prefix="/api")
    api.include_router(learning.router, prefix="/api")


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Apply credentials saved from the web UI (survive restarts).
        try:
            from app.services.config_store import apply_overrides_on_startup  # noqa: PLC0415

            apply_overrides_on_startup()
        except Exception as exc:  # noqa: BLE001
            logger.warning("web credentials overrides not applied: %s", exc)
        try:
            from app.tasks.scheduler import start_scheduler  # noqa: PLC0415

            start_scheduler()
        except Exception as exc:  # noqa: BLE001
            logger.warning("scheduler not available: %s", exc)
        yield

    app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    _register_routers(app)

    if _DIST_DIR.exists():
        assets = _DIST_DIR / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            if full_path.startswith("api/"):
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    {"success": False, "error": {"code": "NOT_FOUND", "message": "Endpoint not found."}},
                    status_code=404,
                )
            candidate = _DIST_DIR / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            index = _DIST_DIR / "index.html"
            if index.exists():
                return FileResponse(index)
            return {"detail": "Frontend not built. Run: cd frontend && npm run build"}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn  # noqa: PLC0415

    s = get_settings()
    uvicorn.run("app.main:app", host=s.APP_HOST, port=s.APP_PORT, reload=False)
