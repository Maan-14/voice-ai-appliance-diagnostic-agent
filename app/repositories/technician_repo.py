from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.technician import Technician
from app.models.service_area import ServiceArea
from app.models.specialty import Specialty
from app.repositories.base import BaseRepository


class TechnicianRepository(BaseRepository[Technician]):
    model = Technician

    async def list_with_relations(self) -> Sequence[Technician]:
        stmt = select(Technician).options(
            selectinload(Technician.service_areas),
            selectinload(Technician.specialties),
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
