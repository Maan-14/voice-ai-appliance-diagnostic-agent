from __future__ import annotations

from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.call_record import CallOutcome, CallRecord
from app.repositories.base import BaseRepository


class CallRecordRepository(BaseRepository[CallRecord]):
    model = CallRecord

    async def get_by_sid(self, call_sid: str) -> CallRecord | None:
        stmt = select(CallRecord).where(CallRecord.call_sid == call_sid)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_recent(self, limit: int = 50) -> Sequence[CallRecord]:
        stmt = (
            select(CallRecord)
            .options(
                selectinload(CallRecord.customer),
                selectinload(CallRecord.appointment),
            )
            .order_by(CallRecord.created_at.desc())
            .limit(limit)
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def get_with_relations(self, call_id: int) -> CallRecord | None:
        stmt = (
            select(CallRecord)
            .where(CallRecord.id == call_id)
            .options(
                selectinload(CallRecord.customer),
                selectinload(CallRecord.appointment),
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def count_all(self) -> int:
        return int(
            (await self.session.execute(select(func.count()).select_from(CallRecord))).scalar_one()
        )

    async def count_with_diagnosis(self) -> int:
        stmt = (
            select(func.count())
            .select_from(CallRecord)
            .where(CallRecord.diagnosis_summary.is_not(None))
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_by_outcome(self, outcome: CallOutcome) -> int:
        stmt = select(func.count()).select_from(CallRecord).where(CallRecord.outcome == outcome)
        return int((await self.session.execute(stmt)).scalar_one())
