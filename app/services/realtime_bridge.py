"""Bidirectional bridge: Twilio Media Streams (μ-law/8 kHz) ⇄ OpenAI Realtime API.

Responsibilities:
- Open the Realtime websocket and configure the session (voice, format,
  tools, system instructions).
- Forward audio frames in both directions.
- When the model emits a function call, validate the arguments through our
  Pydantic schemas and dispatch to the corresponding handler. Send the
  result back as a `function_call_output` so the model can continue.
- Persist the call record to the DB on hangup.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

import websockets
from fastapi import WebSocket, WebSocketDisconnect

from app.agents.prompts import REALTIME_GREETING, SYSTEM_PROMPT
from app.agents.tool_registry import ToolRegistry, build_tool_registry
from app.agents.tools import ToolContext
from app.config.logging_config import get_logger
from app.config.settings import get_settings
from app.database.session import db_manager
from app.dto.call import CallContextDTO
from app.models.call_record import CallOutcome, CallRecord
from app.repositories.call_repo import CallRecordRepository
from app.repositories.customer_repo import CustomerRepository
from app.services.call_session_store import call_session_store
from app.utils.helpers import normalize_phone

logger = get_logger(__name__)

REALTIME_URL_TMPL = "wss://api.openai.com/v1/realtime?model={model}"


class RealtimeBridge:
    """Single-call bridge — instantiate per Twilio Media Stream connection."""

    def __init__(self, twilio_ws: WebSocket) -> None:
        self._settings = get_settings()
        self._twilio_ws = twilio_ws
        self._openai_ws: Optional[Any] = None
        self._tools: ToolRegistry = build_tool_registry()

        self._stream_sid: Optional[str] = None
        self._call_sid: Optional[str] = None
        self._from_number: Optional[str] = None

        # accumulator for function-call argument deltas keyed by call_id
        self._pending_calls: Dict[str, Dict[str, str]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def run(self) -> None:
        await self._twilio_ws.accept()
        logger.info("Twilio Media Stream WebSocket accepted")

        url = REALTIME_URL_TMPL.format(model=self._settings.openai.realtime_model)
        headers = {
            "Authorization": f"Bearer {self._settings.openai.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        try:
            async with websockets.connect(url, additional_headers=headers) as oai_ws:
                self._openai_ws = oai_ws
                await self._configure_session()

                await asyncio.gather(
                    self._pump_twilio_to_openai(),
                    self._pump_openai_to_twilio(),
                )
        except WebSocketDisconnect:
            logger.info("Twilio disconnected")
        except Exception:
            logger.exception("Realtime bridge error")
        finally:
            await self._on_call_ended()

    # ------------------------------------------------------------------
    # Session config
    # ------------------------------------------------------------------
    async def _configure_session(self) -> None:
        assert self._openai_ws is not None
        await self._openai_ws.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "modalities": ["audio", "text"],
                        "instructions": SYSTEM_PROMPT,
                        "voice": self._settings.openai.tts_voice,
                        "input_audio_format": "g711_ulaw",
                        "output_audio_format": "g711_ulaw",
                        "input_audio_transcription": {"model": "whisper-1"},
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.5,
                            "prefix_padding_ms": 250,
                            "silence_duration_ms": 600,
                        },
                        "tools": self._tools.realtime_specs(),
                        "tool_choice": "auto",
                    },
                }
            )
        )

    async def _send_initial_greeting(self) -> None:
        """Have the model speak the greeting before listening for the caller."""
        assert self._openai_ws is not None
        await self._openai_ws.send(
            json.dumps(
                {
                    "type": "response.create",
                    "response": {
                        "modalities": ["audio", "text"],
                        "instructions": (
                            f"Say exactly this in a warm, professional tone: "
                            f"\"{REALTIME_GREETING}\""
                        ),
                    },
                }
            )
        )

    # ------------------------------------------------------------------
    # Twilio -> OpenAI
    # ------------------------------------------------------------------
    async def _pump_twilio_to_openai(self) -> None:
        assert self._openai_ws is not None
        async for raw in self._twilio_ws.iter_text():
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue

            etype = event.get("event")
            if etype == "start":
                start = event.get("start", {})
                self._stream_sid = event.get("streamSid")
                self._call_sid = start.get("callSid")
                custom = start.get("customParameters") or {}
                self._from_number = custom.get("from") or start.get("from")
                logger.info(
                    "Twilio stream started | streamSid={} callSid={}",
                    self._stream_sid, self._call_sid,
                )
                if self._call_sid:
                    await call_session_store.get_or_create(
                        self._call_sid, from_number=self._from_number
                    )
                await self._send_initial_greeting()

            elif etype == "media":
                payload = event["media"]["payload"]
                await self._openai_ws.send(
                    json.dumps(
                        {"type": "input_audio_buffer.append", "audio": payload}
                    )
                )

            elif etype == "stop":
                logger.info("Twilio stream stopped | callSid={}", self._call_sid)
                break

    # ------------------------------------------------------------------
    # OpenAI -> Twilio
    # ------------------------------------------------------------------
    async def _pump_openai_to_twilio(self) -> None:
        assert self._openai_ws is not None
        async for raw in self._openai_ws:
            event = json.loads(raw)
            etype = event.get("type")

            if etype == "response.audio.delta":
                await self._send_audio_to_twilio(event["delta"])

            elif etype == "response.audio_transcript.done":
                transcript = event.get("transcript", "")
                if transcript and self._call_sid:
                    ctx = await call_session_store.get(self._call_sid)
                    if ctx:
                        ctx.add_turn("agent", transcript)

            elif etype == "conversation.item.input_audio_transcription.completed":
                transcript = event.get("transcript", "")
                if transcript and self._call_sid:
                    ctx = await call_session_store.get(self._call_sid)
                    if ctx:
                        ctx.add_turn("caller", transcript)

            elif etype == "response.function_call_arguments.delta":
                call_id = event.get("call_id") or event.get("item_id")
                if call_id is None:
                    continue
                slot = self._pending_calls.setdefault(
                    call_id, {"name": event.get("name", ""), "args": ""}
                )
                slot["args"] += event.get("delta", "")
                if event.get("name"):
                    slot["name"] = event["name"]

            elif etype == "response.function_call_arguments.done":
                await self._handle_tool_call(event)

            elif etype == "error":
                logger.warning("Realtime error event | {}", event.get("error"))

    async def _send_audio_to_twilio(self, payload_b64: str) -> None:
        if not self._stream_sid:
            return
        await self._twilio_ws.send_json(
            {
                "event": "media",
                "streamSid": self._stream_sid,
                "media": {"payload": payload_b64},
            }
        )

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------
    async def _handle_tool_call(self, event: Dict[str, Any]) -> None:
        assert self._openai_ws is not None
        call_id = event.get("call_id") or event.get("item_id")
        name = event.get("name") or self._pending_calls.get(call_id, {}).get("name", "")
        args_raw = event.get("arguments") or self._pending_calls.get(call_id, {}).get("args", "{}")
        self._pending_calls.pop(call_id, None)

        try:
            args = json.loads(args_raw or "{}")
        except json.JSONDecodeError:
            args = {}

        result = await self._invoke_tool(name, args)

        await self._openai_ws.send(
            json.dumps(
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(result),
                    },
                }
            )
        )
        # Trigger the model to continue the conversation with the tool result.
        await self._openai_ws.send(json.dumps({"type": "response.create"}))

    async def _invoke_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self._call_sid:
            return {"status": "error", "message": "Call not yet identified."}

        ctx_dto: CallContextDTO = await call_session_store.get_or_create(
            self._call_sid, from_number=self._from_number
        )
        try:
            async with db_manager.session() as session:
                tool_ctx = ToolContext(session=session, call=ctx_dto)
                logger.info("Tool call | name={} sid={}", name, self._call_sid)
                return await self._tools.invoke(name, args, tool_ctx)
        except KeyError:
            return {"status": "error", "message": f"Unknown tool {name!r}."}
        except Exception as exc:
            logger.exception("Tool execution failed | name={}", name)
            return {"status": "error", "message": str(exc)}

    # ------------------------------------------------------------------
    # Persist on hangup
    # ------------------------------------------------------------------
    async def _on_call_ended(self) -> None:
        if not self._call_sid:
            return
        ctx = await call_session_store.remove(self._call_sid)
        if ctx is None:
            return
        try:
            async with db_manager.session() as session:
                repo = CallRecordRepository(session)
                if await repo.get_by_sid(self._call_sid):
                    return

                customer_id: int | None = None
                phone = normalize_phone(ctx.from_number) if ctx.from_number else None
                if phone:
                    customer = await CustomerRepository(session).upsert(
                        phone=phone,
                        name=ctx.customer_name,
                        email=ctx.customer_email,
                        default_address=ctx.customer_address,
                        default_zip=ctx.customer_zip,
                    )
                    customer_id = customer.id

                outcome_map = {
                    "self_resolved": CallOutcome.SELF_RESOLVED,
                    "appointment_booked": CallOutcome.APPOINTMENT_BOOKED,
                    "image_requested": CallOutcome.IMAGE_REQUESTED,
                }
                outcome = outcome_map.get(ctx.outcome or "", CallOutcome.DROPPED)

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
            logger.info(
                "CallRecord persisted | sid={} customer={} outcome={}",
                self._call_sid, customer_id, outcome,
            )
        except Exception:
            logger.exception("Failed to persist CallRecord | sid={}", self._call_sid)
