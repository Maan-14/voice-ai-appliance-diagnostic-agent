from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.config.settings import get_settings

router = APIRouter(tags=["health"])


@router.get("/")
async def root() -> dict:
    settings = get_settings()
    return {
        "service": settings.app.name,
        "env": settings.app.env,
        "version": __version__,
        "status": "ok",
    }


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}
