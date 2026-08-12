"""Conversation persistence repository."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.models.conversation import (
    Conversation,
    ConversationMessage,
    ConversationMode,
    ConversationStatus,
    ConversationToolEvent,
)
from app.repositories.base import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    model = Conversation

    async def get_by_public_id(self, public_id: str) -> Conversation | None:
        stmt = (
            select(Conversation)
            .where(Conversation.public_id == public_id)
            .options(
                selectinload(Conversation.messages),
                selectinload(Conversation.tool_events),
                selectinload(Conversation.customer),
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_external_sid(self, external_sid: str) -> Conversation | None:
        stmt = select(Conversation).where(Conversation.external_sid == external_sid)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create_session(
        self,
        *,
        mode: ConversationMode,
        external_sid: str,
        greeting: str,
    ) -> Conversation:
        conv = Conversation(
            public_id=uuid.uuid4().hex[:16],
            external_sid=external_sid,
            mode=mode,
            title="New conversation",
            status=ConversationStatus.ACTIVE,
            archived=False,
        )
        await self.add(conv)
        msg = ConversationMessage(
            conversation_id=conv.id,
            role="assistant",
            content=greeting,
            sequence=1,
        )
        self.session.add(msg)
        await self.session.flush()
        await self.session.refresh(conv)
        return conv

    async def append_message(
        self,
        conversation: Conversation,
        *,
        role: str,
        content: str,
    ) -> ConversationMessage:
        result = await self.session.execute(
            select(func.coalesce(func.max(ConversationMessage.sequence), 0)).where(
                ConversationMessage.conversation_id == conversation.id
            )
        )
        seq = int(result.scalar_one()) + 1
        msg = ConversationMessage(
            conversation_id=conversation.id,
            role=role,
            content=content,
            sequence=seq,
        )
        self.session.add(msg)
        conversation.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return msg

    async def append_tool_events(
        self,
        conversation: Conversation,
        events: List[Dict[str, Any]],
    ) -> None:
        for e in events:
            self.session.add(
                ConversationToolEvent(
                    conversation_id=conversation.id,
                    tool_name=str(e.get("name") or "tool"),
                    status=str((e.get("result") or {}).get("status") or "ok"),
                    metadata_json=json.dumps(
                        {"args": e.get("args"), "result": e.get("result")},
                        default=str,
                    )[:8000],
                )
            )
        await self.session.flush()

    async def sync_from_call_context(
        self,
        conversation: Conversation,
        call_ctx: Dict[str, Any],
        *,
        diagnosis: Optional[Dict[str, Any]] = None,
    ) -> None:
        conversation.appliance_type = call_ctx.get("appliance_type") or conversation.appliance_type
        conversation.diagnosis_summary = (
            call_ctx.get("diagnosis_summary") or conversation.diagnosis_summary
        )
        conversation.outcome = call_ctx.get("outcome") or conversation.outcome
        if diagnosis:
            conversation.severity = str(diagnosis.get("severity") or conversation.severity or "")
            if diagnosis.get("diagnosis_summary"):
                conversation.diagnosis_summary = diagnosis["diagnosis_summary"]
        if call_ctx.get("booked_appointment_id"):
            conversation.appointment_id = call_ctx["booked_appointment_id"]
        conversation.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

    async def set_agent_history(self, conversation: Conversation, history: List[Any]) -> None:
        conversation.agent_history_json = json.dumps(history, default=str)
        await self.session.flush()

    async def maybe_set_title(self, conversation: Conversation, user_text: str) -> None:
        """Deprecated no-op — titles are AI-generated via title_service."""
        del conversation, user_text
        return None

    async def list_history(
        self,
        *,
        mode: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 50,
        include_archived: bool = False,
    ) -> Sequence[Conversation]:
        # Only surface conversations where the user actually sent a message.
        # Greeting-only / never-started sessions stay out of history.
        has_user_message = (
            select(ConversationMessage.id)
            .where(
                ConversationMessage.conversation_id == Conversation.id,
                ConversationMessage.role == "user",
            )
            .exists()
        )
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.customer))
            .where(has_user_message)
        )
        if not include_archived:
            stmt = stmt.where(Conversation.archived.is_(False))
        if mode in ("text", "voice"):
            stmt = stmt.where(Conversation.mode == ConversationMode(mode))
        if query:
            q = f"%{query.strip()}%"
            msg_ids = select(ConversationMessage.conversation_id).where(
                ConversationMessage.content.ilike(q)
            )
            stmt = stmt.where(
                or_(
                    Conversation.title.ilike(q),
                    Conversation.diagnosis_summary.ilike(q),
                    Conversation.id.in_(msg_ids),
                )
            )
        stmt = stmt.order_by(Conversation.updated_at.desc()).limit(limit)
        return (await self.session.execute(stmt)).scalars().all()

    async def archive(self, conversation: Conversation) -> None:
        conversation.archived = True
        conversation.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

    async def rename(self, conversation: Conversation, title: str) -> None:
        conversation.title = (title or "").strip()[:120] or conversation.title
        conversation.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

    async def complete(
        self,
        conversation: Conversation,
        *,
        duration_seconds: Optional[int] = None,
    ) -> None:
        conversation.status = ConversationStatus.COMPLETED
        conversation.ended_at = datetime.now(timezone.utc)
        if duration_seconds is not None:
            conversation.duration_seconds = duration_seconds
        conversation.updated_at = conversation.ended_at
        await self.session.flush()
