from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.appointment import Appointment, AppointmentStatus
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

    async def list_with_relations(
        self,
        *,
        limit: int = 100,
        status: Optional[AppointmentStatus] = None,
        appliance_type: Optional[str] = None,
        technician_id: Optional[int] = None,
        service_zip: Optional[str] = None,
        not_before: Optional[datetime] = None,
        not_after: Optional[datetime] = None,
    ) -> Sequence[Appointment]:
        stmt = (
            select(Appointment)
            .options(
                selectinload(Appointment.customer),
                selectinload(Appointment.technician),
            )
            .order_by(Appointment.scheduled_start.desc())
            .limit(limit)
        )
        if status is not None:
            stmt = stmt.where(Appointment.status == status)
        if appliance_type:
            stmt = stmt.where(Appointment.appliance_type == appliance_type)
        if technician_id is not None:
            stmt = stmt.where(Appointment.technician_id == technician_id)
        if service_zip:
            stmt = stmt.where(Appointment.service_zip == service_zip)
        if not_before is not None:
            stmt = stmt.where(Appointment.scheduled_start >= not_before)
        if not_after is not None:
            stmt = stmt.where(Appointment.scheduled_start <= not_after)
        return (await self.session.execute(stmt)).scalars().all()

    async def count_all(self) -> int:
        return int(
            (await self.session.execute(select(func.count()).select_from(Appointment))).scalar_one()
        )

    async def count_open_slots(self) -> int:
        """Unbooked slots that are still in the future (true capacity)."""
        now = datetime.now(timezone.utc)
        stmt = (
            select(func.count())
            .select_from(Availability)
            .where(
                Availability.is_booked.is_(False),
                Availability.start_at >= now,
            )
        )
        return int((await self.session.execute(stmt)).scalar_one())
