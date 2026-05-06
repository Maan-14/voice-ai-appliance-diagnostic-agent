from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.upload_link import UploadLink
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
