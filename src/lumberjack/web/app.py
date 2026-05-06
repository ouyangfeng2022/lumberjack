from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routes import router as api_router

_STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    """Create the FastAPI application with API routes and static file serving."""
    app = FastAPI(title="Lumberjack Markdown Splitter")

    app.include_router(api_router, prefix="/lumber/api")
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
    return app
