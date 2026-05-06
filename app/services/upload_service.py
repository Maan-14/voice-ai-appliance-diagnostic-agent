"""Upload service — issues unique upload links and persists uploaded files."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.logging_config import get_logger
from app.config.settings import get_settings
from app.dto.upload import UploadLinkDTO, UploadResultDTO
from app.models.upload_link import UploadLink, UploadStatus
from app.repositories.customer_repo import CustomerRepository
from app.repositories.upload_repo import UploadLinkRepository
from app.utils.helpers import generate_token, normalize_phone, utc_now

logger = get_logger(__name__)


class UploadError(Exception):
    pass


class UploadService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = UploadLinkRepository(session)
        self.customers = CustomerRepository(session)
        self._settings = get_settings()
        self._settings.upload.directory.mkdir(parents=True, exist_ok=True)

    def _public_upload_url(self, token: str) -> str:
        base = self._settings.app.public_url.rstrip("/")
        return f"{base}/upload/{token}"

    async def issue_link(
        self,
        customer_email: str,
        customer_phone: str,
        appliance_type: Optional[str] = None,
        call_sid: Optional[str] = None,
    ) -> UploadLinkDTO:
        phone_norm = normalize_phone(customer_phone) or customer_phone
        customer = await self.customers.upsert(phone=phone_norm, email=customer_email)

        token = generate_token(24)
        expires_at = utc_now() + timedelta(hours=self._settings.upload.link_ttl_hours)

        link = UploadLink(
            token=token,
            customer_id=customer.id,
            call_sid=call_sid,
            appliance_type=appliance_type,
            expires_at=expires_at,
            status=UploadStatus.PENDING,
        )
        link = await self.repo.add(link)
        logger.info(
            "Issued upload link | token={} customer={} email={}",
            token, customer.id, customer.email,
        )

        return UploadLinkDTO(
            id=link.id,
            token=link.token,
            customer_id=customer.id,
            customer_email=customer.email,
            appliance_type=link.appliance_type,
            expires_at=link.expires_at,
            status=link.status,
            upload_url=self._public_upload_url(token),
        )

    async def store_upload(
        self,
        token: str,
        filename: str,
        content: bytes,
    ) -> Path:
        link = await self.repo.get_by_token(token)
        if link is None:
            raise UploadError("Upload link not found")
        if link.expires_at < utc_now():
            link.status = UploadStatus.EXPIRED
            await self.session.flush()
            raise UploadError("Upload link expired")
        if len(content) > self._settings.upload.max_bytes:
            raise UploadError("File exceeds maximum size")

        safe_name = Path(filename).name  # strip path components
        target_dir = self._settings.upload.directory / token
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / safe_name
        target.write_bytes(content)

        link.stored_path = str(target)
        link.status = UploadStatus.UPLOADED
        await self.session.flush()
        logger.info("Stored upload | token={} path={}", token, target)
        return target

    async def attach_analysis(self, token: str, summary: str) -> UploadResultDTO:
        link = await self.repo.get_by_token(token)
        if link is None:
            raise UploadError("Upload link not found")
        link.analysis_summary = summary
        link.status = UploadStatus.ANALYZED
        await self.session.flush()
        return UploadResultDTO(
            token=token,
            status=link.status,
            stored_path=link.stored_path,
            analysis_summary=summary,
        )
