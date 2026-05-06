from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.appointment import Appointment
from app.models.availability import Availability
from app.models.technician import Technician
from app.repositories.base import BaseRepository


class AppointmentRepository(BaseRepository[Appointment]):
    model = Appointment

    async def get_by_confirmation(self, code: str) -> Appointment | None:
        stmt = select(Appointment).where(Appointment.confirmation_code == code)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def find_open_slots(
        self,
        technician_ids: Sequence[int],
        not_before: datetime,
        limit: int = 20,
    ) -> Sequence[Availability]:
        if not technician_ids:
            return []
        stmt = (
            select(Availability)
            .join(Technician, Availability.technician_id == Technician.id)
            .where(
                Availability.technician_id.in_(technician_ids),
                Availability.is_booked.is_(False),
                Availability.start_at >= not_before,
            )
            .options(selectinload(Availability.technician))
            .order_by(Availability.start_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_availability(self, availability_id: int) -> Availability | None:
        stmt = (
            select(Availability)
            .where(Availability.id == availability_id)
            .options(selectinload(Availability.technician))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
