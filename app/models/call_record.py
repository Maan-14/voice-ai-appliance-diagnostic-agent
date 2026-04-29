from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.customer import Customer


class CallOutcome(str, Enum):
    IN_PROGRESS = "in_progress"
    SELF_RESOLVED = "self_resolved"
    APPOINTMENT_BOOKED = "appointment_booked"
    IMAGE_REQUESTED = "image_requested"
    DROPPED = "dropped"


class CallRecord(Base, TimestampMixin):
    """Persistent record of one inbound diagnostic call.

    Created at call start, finalised at hangup. Linked to a Customer once
    we've identified them, and to an Appointment if the call resulted in
    a booking.
    """

    __tablename__ = "call_records"
    __table_args__ = (
        Index("ix_call_customer", "customer_id"),
        Index("ix_call_appointment", "appointment_id"),
        Index("ix_call_outcome", "outcome"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    call_sid: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    # --- Foreign keys (both nullable — call may not identify either) ----
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), nullable=True
    )
    appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True
    )

    # --- Captured fields ------------------------------------------------
    from_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_number: Mapped[str | None] = mapped_column(String(32), nullable=True)

    appliance_type: Mapped[str | None] = mapped_column(String(48), nullable=True)
    symptoms: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_codes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    diagnosis_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[CallOutcome] = mapped_column(
        SAEnum(CallOutcome, name="call_outcome"),
        nullable=False,
        default=CallOutcome.IN_PROGRESS,
    )

    # --- Relationships --------------------------------------------------
    customer: Mapped["Customer | None"] = relationship(back_populates="call_records")
    appointment: Mapped["Appointment | None"] = relationship(back_populates="call_records")
