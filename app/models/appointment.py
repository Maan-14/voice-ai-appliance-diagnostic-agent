from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.call_record import CallRecord
    from app.models.customer import Customer
    from app.models.technician import Technician


class AppointmentStatus(str, Enum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class Appointment(Base, TimestampMixin):
    __tablename__ = "appointments"
    __table_args__ = (
        Index("ix_appt_customer", "customer_id"),
        Index("ix_appt_tech_time", "technician_id", "scheduled_start"),
        Index("ix_appt_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # --- Foreign keys ---------------------------------------------------
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    technician_id: Mapped[int] = mapped_column(
        ForeignKey("technicians.id", ondelete="RESTRICT"), nullable=False
    )
    availability_id: Mapped[int | None] = mapped_column(
        ForeignKey("availabilities.id", ondelete="SET NULL"), nullable=True
    )

    # --- Service-time snapshot (may differ from customer's defaults) ----
    service_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    service_zip: Mapped[str] = mapped_column(String(12), nullable=False)

    appliance_type: Mapped[str] = mapped_column(String(48), nullable=False)
    issue_summary: Mapped[str] = mapped_column(Text, nullable=False)

    scheduled_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    scheduled_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    status: Mapped[AppointmentStatus] = mapped_column(
        SAEnum(AppointmentStatus, name="appointment_status"),
        nullable=False,
        default=AppointmentStatus.SCHEDULED,
    )

    confirmation_code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)

    # --- Relationships --------------------------------------------------
    customer: Mapped["Customer"] = relationship(back_populates="appointments")
    technician: Mapped["Technician"] = relationship(back_populates="appointments")
    call_records: Mapped[List["CallRecord"]] = relationship(
        back_populates="appointment", passive_deletes=True
    )
