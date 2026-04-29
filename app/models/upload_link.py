from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.customer import Customer


class UploadStatus(str, Enum):
    PENDING = "pending"
    UPLOADED = "uploaded"
    ANALYZED = "analyzed"
    EXPIRED = "expired"


class UploadLink(Base, TimestampMixin):
    __tablename__ = "upload_links"
    __table_args__ = (
        Index("ix_upload_customer", "customer_id"),
        Index("ix_upload_call_sid", "call_sid"),
        Index("ix_upload_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    # --- Foreign key ----------------------------------------------------
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )

    # --- Lookup helpers (no FK because CallRecord may not exist yet) ----
    call_sid: Mapped[str | None] = mapped_column(String(64), nullable=True)

    appliance_type: Mapped[str | None] = mapped_column(String(48), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[UploadStatus] = mapped_column(
        SAEnum(UploadStatus, name="upload_status"),
        nullable=False,
        default=UploadStatus.PENDING,
    )

    stored_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    analysis_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Relationships --------------------------------------------------
    customer: Mapped["Customer"] = relationship(back_populates="upload_links")
