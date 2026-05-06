from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.technician import Technician


class Specialty(Base, TimestampMixin):
    __tablename__ = "specialties"
    __table_args__ = (
        UniqueConstraint(
            "technician_id", "appliance_type", name="uq_specialty_tech_appliance"
        ),
        Index("ix_specialty_tech", "technician_id"),
        Index("ix_specialty_appliance", "appliance_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    technician_id: Mapped[int] = mapped_column(
        ForeignKey("technicians.id", ondelete="CASCADE"), nullable=False
    )
    appliance_type: Mapped[str] = mapped_column(String(48), nullable=False)
    proficiency: Mapped[str] = mapped_column(
        String(16), nullable=False, default="standard"
    )

    technician: Mapped["Technician"] = relationship(back_populates="specialties")
