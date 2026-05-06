from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.technician import Technician


class ServiceArea(Base, TimestampMixin):
    __tablename__ = "service_areas"
    __table_args__ = (
        UniqueConstraint("technician_id", "zip_code", name="uq_service_area_tech_zip"),
        Index("ix_service_areas_tech", "technician_id"),
        Index("ix_service_areas_zip", "zip_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    technician_id: Mapped[int] = mapped_column(
        ForeignKey("technicians.id", ondelete="CASCADE"), nullable=False
    )
    zip_code: Mapped[str] = mapped_column(String(12), nullable=False)

    technician: Mapped["Technician"] = relationship(back_populates="service_areas")
