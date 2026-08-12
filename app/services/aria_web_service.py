"""Thin session orchestration for the ARIA web product UI.

Reuses DiagnosticAgent + tools + repositories — no duplicated business logic.
Persists every text/voice turn to Conversation tables automatically.
"""
from __future__ import annotations

import json
import uuid
from io import BytesIO
from typing import Any, AsyncIterator, Dict, List, Optional

from agents import Runner
from agents.stream_events import RawResponsesStreamEvent
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent

from app.agents.diagnostic_agent import diagnostic_agent_factory
from app.agents.prompts import REALTIME_GREETING
from app.agents.tools import ToolContext
from app.config.settings import get_settings
from app.database.session import db_manager
from app.dto.call import CallContextDTO
from app.models.call_record import CallOutcome, CallRecord
from app.models.conversation import ConversationMode
from app.repositories.call_repo import CallRecordRepository
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.customer_repo import CustomerRepository
from app.services.openai_client import openai_client_factory
from app.utils.helpers import normalize_phone


def _sse(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def _serialize_conversation(conv: Any, *, include_messages: bool = False) -> Dict[str, Any]:
    messages = []
    if include_messages and getattr(conv, "messages", None) is not None:
        messages = [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "timestamp": m.created_at.isoformat() if m.created_at else None,
                "sequence": m.sequence,
            }
            for m in sorted(conv.messages, key=lambda x: x.sequence)
        ]
    tools = []
    if include_messages and getattr(conv, "tool_events", None) is not None:
        tools = [
            {
                "tool_name": t.tool_name,
                "status": t.status,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in conv.tool_events
        ]
    history: List[Any] = []
    if conv.agent_history_json:
        try:
            history = json.loads(conv.agent_history_json)
        except json.JSONDecodeError:
            history = []

    return {
        "id": conv.public_id,
        "mode": conv.mode.value if hasattr(conv.mode, "value") else str(conv.mode),
        "title": conv.title,
        "status": conv.status.value if hasattr(conv.status, "value") else str(conv.status),
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
        "ended_at": conv.ended_at.isoformat() if conv.ended_at else None,
        "duration_seconds": conv.duration_seconds,
        "appliance": conv.appliance_type,
        "severity": conv.severity,
        "diagnosis": conv.diagnosis_summary,
        "outcome": conv.outcome,
        "appointment_id": conv.appointment_id,
        "external_sid": conv.external_sid,
        "messages": messages,
        "tool_events": tools,
        "history": history,
        "call_context": {
            "call_sid": conv.external_sid,
            "from_number": "+13125550000",
            "appliance_type": conv.appliance_type,
            "diagnosis_summary": conv.diagnosis_summary,
            "outcome": conv.outcome,
            "booked_appointment_id": conv.appointment_id,
            "symptoms": [],
            "error_codes": [],
            "transcript_lines": [],
            "customer_name": None,
            "customer_zip": None,
            "customer_email": None,
            "customer_address": None,
        },
    }


async def create_web_session(mode: str = "text") -> Dict[str, Any]:
    mode_enum = ConversationMode.VOICE if mode == "voice" else ConversationMode.TEXT
    prefix = "voice" if mode_enum == ConversationMode.VOICE else "web"
    external_sid = f"{prefix}-{uuid.uuid4().hex[:12]}"
    ctx = CallContextDTO(call_sid=external_sid, from_number="+13125550000")

    async with db_manager.session() as session:
        repo = ConversationRepository(session)
        conv = await repo.create_session(
            mode=mode_enum,
            external_sid=external_sid,
            greeting=REALTIME_GREETING,
        )
        # Reload with messages
        conv = await repo.get_by_public_id(conv.public_id)
        assert conv is not None
        payload = _serialize_conversation(conv, include_messages=True)
        payload["greeting"] = REALTIME_GREETING
        payload["session_id"] = conv.public_id
        payload["call_context"] = ctx.model_dump(mode="json")
        payload["history"] = []
        return payload


# Back-compat alias used by older imports
def new_web_session() -> Dict[str, Any]:
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(create_web_session("text"))
    raise RuntimeError("Use await create_web_session() from async context")


async def stream_agent_turn(
    *,
    user_message: str,
    call_ctx_data: Dict[str, Any],
    history: List[Any],
    conversation_id: Optional[str] = None,
) -> AsyncIterator[str]:
    call = CallContextDTO.model_validate(call_ctx_data)
    agent = diagnostic_agent_factory.build_agent()
    turn_events: List[Dict[str, Any]] = []
    reply_parts: List[str] = []
    title: Optional[str] = None
    last_diagnosis: Any = None
    events_copy: List[Dict[str, Any]] = []
    reply = ""
    updated_history: List[Any] = []

    async with db_manager.session() as session:
        tool_ctx = ToolContext(session=session, call=call, tool_events=turn_events)
        next_history = list(history)
        next_history.append({"role": "user", "content": user_message})

        yield _sse({"type": "status", "status": "thinking"})

        result = Runner.run_streamed(agent, next_history, context=tool_ctx)
        async for event in result.stream_events():
            if isinstance(event, RawResponsesStreamEvent):
                if isinstance(event.data, ResponseTextDeltaEvent):
                    delta = event.data.delta or ""
                    if delta:
                        reply_parts.append(delta)
                        yield _sse({"type": "delta", "text": delta})

        reply = "".join(reply_parts) or str(result.final_output or "")
        call.add_turn("customer", user_message)
        call.add_turn("agent", reply)
        updated_history = result.to_input_list()
        last_diagnosis = tool_ctx.last_diagnosis
        events_copy = list(tool_ctx.tool_events)

        if conversation_id:
            crepo = ConversationRepository(session)
            conv = await crepo.get_by_public_id(conversation_id)
            if conv is None:
                conv = await crepo.get_by_external_sid(call.call_sid)
            if conv is not None:
                await crepo.append_message(conv, role="user", content=user_message)
                await crepo.append_message(conv, role="assistant", content=reply)
                await crepo.append_tool_events(conv, events_copy)
                await crepo.sync_from_call_context(
                    conv,
                    call.model_dump(mode="json"),
                    diagnosis=last_diagnosis,
                )
                await crepo.set_agent_history(conv, updated_history)

    # Emit done before title generation so voice TTS can flush the final
    # sentence immediately (title assignment is a separate LLM call).
    yield _sse(
        {
            "type": "done",
            "reply": reply,
            "call_context": call.model_dump(mode="json"),
            "history": updated_history,
            "tool_events": events_copy,
            "last_diagnosis": last_diagnosis,
            "conversation_id": conversation_id,
            "title": None,
        }
    )

    if conversation_id:
        from app.services.title_service import maybe_assign_ai_title

        title = await maybe_assign_ai_title(conversation_id)
        if title:
            yield _sse(
                {
                    "type": "title",
                    "title": title,
                    "conversation_id": conversation_id,
                }
            )


async def run_agent_turn_sync(
    *,
    user_message: str,
    call_ctx_data: Dict[str, Any],
    history: List[Any],
    conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Non-streaming turn (voice loop). Title is generated on session end, not here."""
    call = CallContextDTO.model_validate(call_ctx_data)
    agent = diagnostic_agent_factory.build_agent()
    turn_events: List[Dict[str, Any]] = []

    async with db_manager.session() as session:
        tool_ctx = ToolContext(session=session, call=call, tool_events=turn_events)
        next_history = list(history)
        next_history.append({"role": "user", "content": user_message})
        result = await Runner.run(agent, next_history, context=tool_ctx)
        reply = str(result.final_output or "")
        call.add_turn("customer", user_message)
        call.add_turn("agent", reply)
        updated_history = result.to_input_list()

        if conversation_id:
            crepo = ConversationRepository(session)
            conv = await crepo.get_by_public_id(conversation_id)
            if conv is None:
                conv = await crepo.get_by_external_sid(call.call_sid)
            if conv is not None:
                await crepo.append_message(conv, role="user", content=user_message)
                await crepo.append_message(conv, role="assistant", content=reply)
                await crepo.append_tool_events(conv, list(tool_ctx.tool_events))
                await crepo.sync_from_call_context(
                    conv,
                    call.model_dump(mode="json"),
                    diagnosis=tool_ctx.last_diagnosis,
                )
                await crepo.set_agent_history(conv, updated_history)

        return {
            "reply": reply,
            "call_context": call.model_dump(mode="json"),
            "history": updated_history,
            "tool_events": list(tool_ctx.tool_events),
            "last_diagnosis": tool_ctx.last_diagnosis,
            "conversation_id": conversation_id,
        }


async def transcribe_audio(audio_bytes: bytes, filename: str = "utterance.webm") -> str:
    buf = BytesIO(audio_bytes)
    buf.name = filename
    result = await openai_client_factory.client.audio.transcriptions.create(
        model="whisper-1",
        file=buf,
    )
    return (result.text or "").strip()


async def synthesize_speech(text: str) -> bytes:
    settings = get_settings()
    response = await openai_client_factory.client.audio.speech.create(
        model="tts-1",
        voice=settings.openai.tts_voice or "alloy",
        input=text[:4096],
    )
    return response.content


async def persist_session(
    call_ctx_data: Dict[str, Any],
    *,
    conversation_id: Optional[str] = None,
    duration_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """Finalize voice/text: CallRecord (ops) + Conversation completed.

    AI title is assigned *after* mic/TTS lifecycle ends (caller already stopped
    audio). Title generation never triggers TTS.
    """
    ctx = CallContextDTO.model_validate(call_ctx_data)
    public_id: Optional[str] = conversation_id
    result: Dict[str, Any]

    async with db_manager.session() as session:
        crepo = ConversationRepository(session)
        conv = None
        if conversation_id:
            conv = await crepo.get_by_public_id(conversation_id)
        if conv is None:
            conv = await crepo.get_by_external_sid(ctx.call_sid)
        if conv is not None:
            public_id = conv.public_id
            await crepo.sync_from_call_context(conv, ctx.model_dump(mode="json"))
            await crepo.complete(conv, duration_seconds=duration_seconds)

        repo = CallRecordRepository(session)
        existing = await repo.get_by_sid(ctx.call_sid)
        if existing:
            result = {
                "status": "exists",
                "call_sid": ctx.call_sid,
                "conversation_id": public_id,
            }
        else:
            customer_id: Optional[int] = None
            phone = normalize_phone(ctx.from_number) if ctx.from_number else None
            if phone:
                customer = await CustomerRepository(session).upsert(
                    phone=phone,
                    name=ctx.customer_name,
                    email=str(ctx.customer_email) if ctx.customer_email else None,
                    default_address=ctx.customer_address,
                    default_zip=ctx.customer_zip,
                )
                customer_id = customer.id
                if conv is not None:
                    conv.customer_id = customer_id

            outcome_map = {
                "self_resolved": CallOutcome.SELF_RESOLVED,
                "appointment_booked": CallOutcome.APPOINTMENT_BOOKED,
                "image_requested": CallOutcome.IMAGE_REQUESTED,
            }
            outcome = outcome_map.get(ctx.outcome or "", CallOutcome.DROPPED)
            if ctx.diagnosis_summary and outcome == CallOutcome.DROPPED:
                outcome = CallOutcome.IN_PROGRESS

            record = CallRecord(
                call_sid=ctx.call_sid,
                customer_id=customer_id,
                appointment_id=ctx.booked_appointment_id,
                from_number=ctx.from_number,
                appliance_type=ctx.appliance_type,
                symptoms="; ".join(ctx.symptoms) if ctx.symptoms else None,
                error_codes=", ".join(ctx.error_codes) if ctx.error_codes else None,
                diagnosis_summary=ctx.diagnosis_summary,
                transcript="\n".join(ctx.transcript_lines),
                outcome=outcome,
            )
            await repo.add(record)
            result = {
                "status": "ok",
                "call_sid": ctx.call_sid,
                "id": record.id,
                "conversation_id": public_id,
            }

    # After session commit — never speaks; UI already silenced mic/TTS
    if public_id:
        from app.services.title_service import maybe_assign_ai_title

        title = await maybe_assign_ai_title(public_id)
        if title:
            result["title"] = title

    return result


async def list_conversations(
    *,
    mode: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    async with db_manager.session() as session:
        rows = await ConversationRepository(session).list_history(
            mode=mode, query=query, limit=limit
        )
        return [_serialize_conversation(r, include_messages=False) for r in rows]


async def get_conversation(public_id: str) -> Optional[Dict[str, Any]]:
    async with db_manager.session() as session:
        conv = await ConversationRepository(session).get_by_public_id(public_id)
        if not conv or conv.archived:
            return None
        data = _serialize_conversation(conv, include_messages=True)
        # Rebuild call_context from stored fields + last known agent path
        data["call_context"] = CallContextDTO(
            call_sid=conv.external_sid,
            from_number="+13125550000",
            appliance_type=conv.appliance_type,
            diagnosis_summary=conv.diagnosis_summary,
            outcome=conv.outcome,
            booked_appointment_id=conv.appointment_id,
        ).model_dump(mode="json")
        return data


async def rename_conversation(public_id: str, title: str) -> Optional[Dict[str, Any]]:
    async with db_manager.session() as session:
        repo = ConversationRepository(session)
        conv = await repo.get_by_public_id(public_id)
        if not conv:
            return None
        await repo.rename(conv, title)
        return _serialize_conversation(conv)


async def archive_conversation(public_id: str) -> bool:
    async with db_manager.session() as session:
        repo = ConversationRepository(session)
        conv = await repo.get_by_public_id(public_id)
        if not conv:
            return False
        await repo.archive(conv)
        return True


async def ops_summary() -> Dict[str, Any]:
    from app.repositories.appointment_repo import AppointmentRepository
    from app.services.call_session_store import call_session_store

    async with db_manager.session() as session:
        calls = CallRecordRepository(session)
        appts = AppointmentRepository(session)
        crepo = ConversationRepository(session)
        recent_conv = await crepo.list_history(limit=12)
        recent_calls = await calls.list_recent(limit=12)
        live = await call_session_store.all()
        rows = [_serialize_conversation(c) for c in recent_conv]
        call_rows = []
        for r in recent_calls:
            customer = r.__dict__.get("customer")
            call_rows.append(
                {
                    "id": r.id,
                    "name": (customer.name if customer else None) or "Unknown",
                    "mode": "Voice",
                    "appliance": r.appliance_type,
                    "summary": r.diagnosis_summary or r.symptoms or "In progress",
                    "outcome": r.outcome.value if hasattr(r.outcome, "value") else str(r.outcome),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
            )
        return {
            "active_conversations": len(live),
            "total_calls": await calls.count_all(),
            "appointments": await appts.count_all(),
            "recent": rows,
            "recent_calls": call_rows,
            "live": [
                {
                    "call_sid": sid,
                    "name": ctx.customer_name or ctx.from_number or "Caller",
                    "mode": "Voice",
                    "summary": ctx.diagnosis_summary
                    or (ctx.appliance_type and f"Diagnosing {ctx.appliance_type}")
                    or "Live call",
                }
                for sid, ctx in live.items()
            ],
        }
