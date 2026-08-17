from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.upload_link import UploadLink, UploadStatus
from app.repositories.base import BaseRepository


class UploadLinkRepository(BaseRepository[UploadLink]):
    model = UploadLink

    async def get_by_token(self, token: str) -> UploadLink | None:
        stmt = (
            select(UploadLink)
            .where(UploadLink.token == token)
            .options(selectinload(UploadLink.customer))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_call_sid(self, call_sid: str) -> UploadLink | None:
        stmt = select(UploadLink).where(UploadLink.call_sid == call_sid)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_with_customer(
        self,
        *,
        limit: int = 50,
        status: Optional[UploadStatus] = None,
    ) -> Sequence[UploadLink]:
        stmt = (
            select(UploadLink)
            .options(selectinload(UploadLink.customer))
            .order_by(UploadLink.created_at.desc())
            .limit(limit)
        )
        if status is not None:
            stmt = stmt.where(UploadLink.status == status)
        return (await self.session.execute(stmt)).scalars().all()

    async def count_by_status(self, status: UploadStatus) -> int:
        stmt = select(func.count()).select_from(UploadLink).where(UploadLink.status == status)
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_pending_analysis(self) -> int:
        """Links awaiting vision analysis (requested or uploaded, not yet analyzed)."""
        stmt = (
            select(func.count())
            .select_from(UploadLink)
            .where(UploadLink.status.in_([UploadStatus.PENDING, UploadStatus.UPLOADED]))
        )
        return int((await self.session.execute(stmt)).scalar_one())
