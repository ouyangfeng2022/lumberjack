from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routes import router as api_router

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    """Create the FastAPI application.

    The API routes are always registered. The web UI's static assets (produced by
    ``lumberjack_webui``'s build) are mounted only when present, so the server can
    run as a pure API backend when the frontend hasn't been built — e.g. in CI,
    where those assets are excluded from version control.
    """
    app = FastAPI(title="Lumberjack Markdown Splitter")

    app.include_router(api_router, prefix="/lumber/api", tags=["lumber"])

    if _STATIC_DIR.is_dir():
        app.mount(
            "/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static"
        )
    else:
        logger.warning(
            "Static directory %s does not exist; running in API-only mode. "
            "Build the frontend (lumberjack_webui) to serve the web UI.",
            _STATIC_DIR,
        )

    return app
