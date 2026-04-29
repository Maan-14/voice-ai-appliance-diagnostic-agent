"""Reusable FastAPI dependencies.

Anything an endpoint needs that isn't unique to a single endpoint goes
here, exposed as ``Depends(...)``-friendly callables. This keeps route
handlers declarative — they list the resolved values they want and
contain only the logic genuinely specific to that route.

Conventions:
- Service factories are named ``get_<service>_service`` (or ``get_<x>``).
- Resolvers (look up + validate + raise the right HTTPException) are
  named ``resolve_<thing>``.
- Validators turning a raw request body into a typed value are named
  ``validate_<thing>``.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.logging_config import get_logger
from app.config.settings import get_settings
from app.database.session import get_session
from app.dto.call import CallContextDTO
from app.models.upload_link import UploadLink, UploadStatus
from app.repositories.upload_repo import UploadLinkRepository
from app.services.call_session_store import call_session_store
from app.services.scheduling_service import SchedulingService
from app.services.upload_service import UploadService
from app.services.voice_service import VoiceService
from app.utils.helpers import utc_now

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Service factories
# ---------------------------------------------------------------------------

async def get_upload_service(
    session: AsyncSession = Depends(get_session),
) -> UploadService:
    return UploadService(session)


async def get_scheduling_service(
    session: AsyncSession = Depends(get_session),
) -> SchedulingService:
    return SchedulingService(session)


def get_voice_service() -> VoiceService:
    return VoiceService()


# ---------------------------------------------------------------------------
# Resolvers
# ---------------------------------------------------------------------------

async def resolve_active_upload_link(
    token: str,
    session: AsyncSession = Depends(get_session),
) -> UploadLink:
    """Look up an upload link by token, validate it's still usable.

    Raises 404 if missing, 410 if expired. The endpoint receives a
    guaranteed-fresh ``UploadLink`` and can focus on the happy path.
    """
    link = await UploadLinkRepository(session).get_by_token(token)
    if link is None:
        raise HTTPException(status_code=404, detail="Upload link not found")
    if link.expires_at < utc_now():
        raise HTTPException(status_code=410, detail="Upload link has expired")
    return link


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UploadedImage:
    filename: str
    content: bytes


async def validate_image_payload(
    file: UploadFile = File(...),
) -> UploadedImage:
    """Reject non-images / oversize files before they reach the service."""
    settings = get_settings()
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are accepted")

    body = await file.read()
    if len(body) > settings.upload.max_bytes:
        raise HTTPException(status_code=413, detail="File too large")

    return UploadedImage(filename=file.filename or "photo.jpg", content=body)


async def register_inbound_call(
    CallSid: str = Form(default=""),
    From: str = Form(default=""),
    To: str = Form(default=""),
) -> CallContextDTO:
    """Record an inbound Twilio call in the in-memory session store.

    Returns the freshly-created (or already-existing) ``CallContextDTO``
    the rest of the request can use.
    """
    if not CallSid:
        raise HTTPException(status_code=400, detail="Missing CallSid")
    logger.info("Inbound call | sid={} from={} to={}", CallSid, From, To)
    return await call_session_store.get_or_create(
        call_sid=CallSid, from_number=From or None
    )
