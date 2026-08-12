"""Persistent ARIA conversations (text + voice) — separate from phone CallRecord."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Boolean
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, _utcnow

if TYPE_CHECKING:
    from app.models.customer import Customer


class ConversationMode(str, Enum):
    TEXT = "text"
    VOICE = "voice"


class ConversationStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"


class Conversation(Base, TimestampMixin):
    """One ARIA web/text or browser-voice diagnostic session."""

    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conv_public_id", "public_id", unique=True),
        Index("ix_conv_updated", "updated_at"),
        Index("ix_conv_mode_status", "mode", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    # Matches CallContextDTO.call_sid — links to CallRecord when voice/text is finalized
    external_sid: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    customer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    appointment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True
    )

    mode: Mapped[ConversationMode] = mapped_column(
        SAEnum(ConversationMode, name="conversation_mode"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False, default="New conversation")
    status: Mapped[ConversationStatus] = mapped_column(
        SAEnum(ConversationStatus, name="conversation_status"),
        nullable=False,
        default=ConversationStatus.ACTIVE,
    )
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    appliance_type: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    severity: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    diagnosis_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outcome: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)

    # Agents SDK input list (JSON) so chat can resume after refresh
    agent_history_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    messages: Mapped[List["ConversationMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.sequence",
    )
    tool_events: Mapped[List["ConversationToolEvent"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationToolEvent.id",
    )
    customer: Mapped[Optional["Customer"]] = relationship()


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (Index("ix_msg_conversation", "conversation_id", "sequence"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class ConversationToolEvent(Base):
    __tablename__ = "conversation_tool_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ok")
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="tool_events")
