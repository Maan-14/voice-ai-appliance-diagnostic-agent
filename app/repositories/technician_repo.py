from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.availability import Availability
from app.models.technician import Technician
from app.models.service_area import ServiceArea
from app.models.specialty import Specialty
from app.repositories.base import BaseRepository


class TechnicianRepository(BaseRepository[Technician]):
    model = Technician

    async def list_with_relations(self) -> Sequence[Technician]:
        stmt = (
            select(Technician)
            .options(
                selectinload(Technician.service_areas),
                selectinload(Technician.specialties),
                selectinload(Technician.availabilities),
            )
            .order_by(Technician.name.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().unique().all()

    async def find_for_zip_and_appliance(
        self, zip_code: str, appliance_type: str
    ) -> Sequence[Technician]:
        """Technicians who serve `zip_code` and specialise in `appliance_type`."""
        stmt = (
            select(Technician)
            .join(ServiceArea, ServiceArea.technician_id == Technician.id)
            .join(Specialty, Specialty.technician_id == Technician.id)
            .where(
                Technician.is_active.is_(True),
                ServiceArea.zip_code == zip_code,
                Specialty.appliance_type == appliance_type,
            )
            .options(
                selectinload(Technician.service_areas),
                selectinload(Technician.specialties),
            )
            .distinct()
        )
        result = await self.session.execute(stmt)
        return result.scalars().unique().all()

    async def count_active(self) -> int:
        stmt = select(func.count()).select_from(Technician).where(
            Technician.is_active.is_(True)
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def next_open_slot(self, technician_id: int) -> Availability | None:
        now = datetime.now(timezone.utc)
        stmt = (
            select(Availability)
            .where(
                Availability.technician_id == technician_id,
                Availability.is_booked.is_(False),
                Availability.start_at >= now,
            )
            .order_by(Availability.start_at.asc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
