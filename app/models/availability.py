from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.technician import Technician


class Availability(Base, TimestampMixin):
    __tablename__ = "availabilities"
    __table_args__ = (
        UniqueConstraint("technician_id", "start_at", name="uq_avail_tech_start"),
        Index("ix_avail_tech_start", "technician_id", "start_at"),
        Index("ix_avail_open_start", "is_booked", "start_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    technician_id: Mapped[int] = mapped_column(
        ForeignKey("technicians.id", ondelete="CASCADE"), nullable=False
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_booked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    constraint_note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    technician: Mapped["Technician"] = relationship(back_populates="availabilities")
