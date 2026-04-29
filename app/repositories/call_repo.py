from __future__ import annotations

from sqlalchemy import select

from app.models.call_record import CallRecord
from app.repositories.base import BaseRepository


class CallRecordRepository(BaseRepository[CallRecord]):
    model = CallRecord

    async def get_by_sid(self, call_sid: str) -> CallRecord | None:
        stmt = select(CallRecord).where(CallRecord.call_sid == call_sid)
        return (await self.session.execute(stmt)).scalar_one_or_none()
