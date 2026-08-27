from __future__ import annotations

import logging
from pathlib import Path

import anyio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .limits import ServerLimits, package_version
from .middleware import DemoSafetyMiddleware
from .routes import health, version
from .routes import router as api_router

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(
    *, serve_static: bool = True, limits: ServerLimits | None = None
) -> FastAPI:
    """Create the FastAPI application.

    The API routes are always registered. The web UI's static assets (produced by
    ``lumberjack_webui``'s build) are mounted only when present, so the server can
    run as a pure API backend when the frontend hasn't been built — e.g. in CI,
    where those assets are excluded from version control.

    Deployment limits (request size, rate, concurrency, split timeout) come from
    ``LUMBERJACK_WEB_*`` environment variables unless ``limits`` is passed
    explicitly. Health and version endpoints are registered both under
    ``/lumber/api`` and at the top level for load balancers.

    Args:
        serve_static: Mount the built Web UI when available. Tests that exercise
            only the API can disable this to avoid the SPA catch-all route.
        limits: Explicit server limits; defaults to ``ServerLimits.from_env()``.
    """
    resolved_limits = limits if limits is not None else ServerLimits.from_env()
    app = FastAPI(title="Lumberjack Markdown Splitter")
    app.state.limits = resolved_limits
    app.state.split_limiter = anyio.CapacityLimiter(
        resolved_limits.max_concurrent_splits
    )

    app.add_middleware(DemoSafetyMiddleware, limits=resolved_limits)

    app.include_router(api_router, prefix="/lumber/api", tags=["lumber"])

    app.add_api_route("/health", health, tags=["lumber"])
    app.add_api_route("/version", version, tags=["lumber"])
    app.add_api_route("/lumber/api/health", health, tags=["lumber"])
    app.add_api_route("/lumber/api/version", version, tags=["lumber"])

    if serve_static and _STATIC_DIR.is_dir():
        app.mount(
            "/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static"
        )
    elif serve_static:
        logger.warning(
            "Static directory %s does not exist; running in API-only mode. "
            "Build the frontend (lumberjack_webui) to serve the web UI.",
            _STATIC_DIR,
        )

    logger.info(
        "lumberjack web server %s (max_body_bytes=%d, max_concurrent_splits=%d, "
        "split_timeout_seconds=%s, rate_limit=%d/%ss)",
        package_version(),
        resolved_limits.max_body_bytes,
        resolved_limits.max_concurrent_splits,
        resolved_limits.split_timeout_seconds,
        resolved_limits.rate_limit_requests,
        resolved_limits.rate_limit_window_seconds,
    )

    return app
