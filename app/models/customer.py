from __future__ import annotations

from typing import List, TYPE_CHECKING

from sqlalchemy import Boolean, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.call_record import CallRecord
    from app.models.upload_link import UploadLink


class Customer(Base, TimestampMixin):
    """A homeowner who has called us at least once.

    Identified by phone number (E.164). Email and name are optional because
    we may take a call from someone before we've collected those details.
    """

    __tablename__ = "customers"
    __table_args__ = (
        Index("ix_customer_email", "email"),
        Index("ix_customer_zip", "default_zip"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    default_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_zip: Mapped[str | None] = mapped_column(String(12), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    appointments: Mapped[List["Appointment"]] = relationship(
        back_populates="customer", passive_deletes=True
    )
    call_records: Mapped[List["CallRecord"]] = relationship(
        back_populates="customer", passive_deletes=True
    )
    upload_links: Mapped[List["UploadLink"]] = relationship(
        back_populates="customer", passive_deletes=True
    )
