"""Scheduling service — finds matching technicians, lists slots, books appointments."""
from __future__ import annotations

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.logging_config import get_logger
from app.dto.appointment import (
    AppointmentCreateDTO,
    AppointmentDTO,
    AvailabilitySlotDTO,
)
from app.models.appointment import Appointment, AppointmentStatus
from app.repositories.appointment_repo import AppointmentRepository
from app.repositories.customer_repo import CustomerRepository
from app.repositories.technician_repo import TechnicianRepository
from app.utils.helpers import (
    generate_confirmation_code,
    normalize_appliance,
    normalize_phone,
    normalize_zip,
    utc_now,
)

logger = get_logger(__name__)


class SchedulingError(Exception):
    """Domain error raised when a scheduling operation cannot proceed."""


class SchedulingService:
    """Coordinates technician matching and appointment booking.

    All public methods accept a single AsyncSession (the request-scoped
    session) so transactions remain bound to the calling unit of work.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.customers = CustomerRepository(session)
        self.technicians = TechnicianRepository(session)
        self.appointments = AppointmentRepository(session)

    async def find_available_slots(
        self,
        zip_code: str,
        appliance_type: str,
        max_slots: int = 6,
    ) -> List[AvailabilitySlotDTO]:
        zip_norm = normalize_zip(zip_code)
        appliance_norm = normalize_appliance(appliance_type)
        if not zip_norm:
            raise SchedulingError(f"Invalid zip code: {zip_code!r}")
        if not appliance_norm:
            raise SchedulingError(f"Unknown appliance type: {appliance_type!r}")

        techs = await self.technicians.find_for_zip_and_appliance(
            zip_code=zip_norm, appliance_type=appliance_norm
        )
        if not techs:
            logger.info(
                "No technicians match | zip={} appliance={}", zip_norm, appliance_norm
            )
            return []

        tech_ids = [t.id for t in techs]
        tech_lookup = {t.id: t for t in techs}

        slots = await self.appointments.find_open_slots(
            technician_ids=tech_ids,
            not_before=utc_now(),
            limit=max_slots,
        )
        return [
            AvailabilitySlotDTO(
                availability_id=slot.id,
                technician_id=slot.technician_id,
                technician_name=tech_lookup[slot.technician_id].name,
                start_at=slot.start_at,
                end_at=slot.end_at,
            )
            for slot in slots
        ]

    async def book_appointment(self, dto: AppointmentCreateDTO) -> AppointmentDTO:
        slot = await self.appointments.get_availability(dto.availability_id)
        if slot is None:
            raise SchedulingError(f"Availability {dto.availability_id} not found")
        if slot.is_booked:
            raise SchedulingError("Selected slot has just been taken; please pick another")

        phone_norm = normalize_phone(dto.customer_phone) or dto.customer_phone
        zip_norm = normalize_zip(dto.service_zip) or dto.service_zip
        appliance_norm = normalize_appliance(dto.appliance_type) or dto.appliance_type

        # Find or create the customer record so the appointment FK is satisfied.
        customer = await self.customers.upsert(
            phone=phone_norm,
            name=dto.customer_name.strip(),
            email=dto.customer_email,
            default_address=dto.customer_address,
            default_zip=zip_norm,
        )

        appt = Appointment(
            customer_id=customer.id,
            technician_id=slot.technician_id,
            availability_id=slot.id,
            service_address=dto.customer_address,
            service_zip=zip_norm,
            appliance_type=appliance_norm,
            issue_summary=dto.issue_summary.strip(),
            scheduled_start=slot.start_at,
            scheduled_end=slot.end_at,
            status=AppointmentStatus.CONFIRMED,
            confirmation_code=generate_confirmation_code(),
        )
        slot.is_booked = True

        appt = await self.appointments.add(appt)
        logger.info(
            "Booked appointment | id={} code={} customer={} tech={} start={}",
            appt.id, appt.confirmation_code, customer.id, appt.technician_id,
            appt.scheduled_start,
        )

        return AppointmentDTO(
            id=appt.id,
            customer_id=customer.id,
            customer_name=customer.name,
            customer_phone=customer.phone,
            customer_email=customer.email,
            service_address=appt.service_address,
            service_zip=appt.service_zip,
            appliance_type=appt.appliance_type,
            issue_summary=appt.issue_summary,
            technician_id=appt.technician_id,
            technician_name=slot.technician.name,
            scheduled_start=appt.scheduled_start,
            scheduled_end=appt.scheduled_end,
            status=appt.status,
            confirmation_code=appt.confirmation_code,
        )
