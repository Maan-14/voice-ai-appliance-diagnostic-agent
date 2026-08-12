"""FastAPI entrypoint — wires routes, lifespan, logging."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config.logging_config import configure_logging, get_logger
from app.config.settings import get_settings
from app.database.session import dispose_db, init_db
from app.routes import aria_router, health_router, upload_router, voice_router

configure_logging()
logger = get_logger(__name__)

WEB_DIR = Path(__file__).resolve().parents[1] / "web"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info("Starting {} v{} env={}", settings.app.name, __version__, settings.app.env)
    await init_db()
    try:
        yield
    finally:
        logger.info("Shutting down")
        await dispose_db()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app.name,
        version=__version__,
        lifespan=_lifespan,
    )

    app.include_router(voice_router)
    app.include_router(upload_router)
    app.include_router(aria_router)
    app.include_router(health_router)

    if WEB_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="aria-static")

        @app.get("/")
        async def aria_home() -> FileResponse:
            return FileResponse(WEB_DIR / "index.html")

    return app


app = create_app()
