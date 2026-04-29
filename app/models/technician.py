from __future__ import annotations

from typing import List, TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.availability import Availability
    from app.models.service_area import ServiceArea
    from app.models.specialty import Specialty


class Technician(Base, TimestampMixin):
    __tablename__ = "technicians"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    employee_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    employment_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="full_time"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    service_areas: Mapped[List["ServiceArea"]] = relationship(
        back_populates="technician", cascade="all, delete-orphan"
    )
    specialties: Mapped[List["Specialty"]] = relationship(
        back_populates="technician", cascade="all, delete-orphan"
    )
    availabilities: Mapped[List["Availability"]] = relationship(
        back_populates="technician", cascade="all, delete-orphan"
    )
    appointments: Mapped[List["Appointment"]] = relationship(
        back_populates="technician"
    )
