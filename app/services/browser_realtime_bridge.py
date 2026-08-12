"""Browser Talk-to-ARIA bridge: browser mic/speaker ⇄ OpenAI Realtime (PCM16).

Same speech↔speech path as ``scripts/mic_voice.py`` / phone Realtime, but the
API key stays on the server. The browser never talks to OpenAI directly.
"""

from __future__ import annotations

import asyncio
import json
import ssl
from typing import Any, Dict, Optional

import certifi
from fastapi import WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect as ws_connect

from app.agents.prompts import REALTIME_GREETING, SYSTEM_PROMPT
from app.agents.tool_registry import ToolRegistry, build_tool_registry
from app.agents.tools import ToolContext
from app.config.logging_config import get_logger
from app.config.settings import get_settings
from app.database.session import db_manager
from app.dto.call import CallContextDTO
from app.services import aria_web_service as aria_svc

logger = get_logger(__name__)

SAMPLE_RATE = 24_000
REALTIME_URL_TMPL = "wss://api.openai.com/v1/realtime?model={model}"


def _openai_ssl_context() -> ssl.SSLContext:
    """Use certifi CAs — macOS Python builds often lack system trust store."""
    return ssl.create_default_context(cafile=certifi.where())


class BrowserRealtimeBridge:
    """One browser voice session → one OpenAI Realtime WebSocket."""

    def __init__(self, browser_ws: WebSocket) -> None:
        self._settings = get_settings()
        self._browser_ws = browser_ws
        self._openai_ws: Optional[Any] = None
        self._tools: ToolRegistry = build_tool_registry()
        self._pending_calls: Dict[str, Dict[str, str]] = {}
        self._call_ctx: Optional[CallContextDTO] = None
        self._conversation_id: Optional[str] = None
        self._started_at: float = 0.0
        self._closed = False

    async def run(self) -> None:
        await self._browser_ws.accept()
        if not (self._settings.openai.api_key or "").startswith("sk-"):
            await self._send_browser({"type": "error", "message": "OpenAI API key is not configured."})
            await self._browser_ws.close()
            return

        url = REALTIME_URL_TMPL.format(model=self._settings.openai.realtime_model)
        headers = {"Authorization": f"Bearer {self._settings.openai.api_key}"}

        try:
            async with ws_connect(
                url,
                additional_headers=headers,
                ssl=_openai_ssl_context(),
            ) as oai_ws:
                self._openai_ws = oai_ws
                await self._wait_for_start()
                await self._configure_session()
                await self._send_browser(
                    {
                        "type": "ready",
                        "sample_rate": SAMPLE_RATE,
                        "conversation_id": self._conversation_id,
                    }
                )
                await self._send_initial_greeting()

                await asyncio.gather(
                    self._pump_browser_to_openai(),
                    self._pump_openai_to_browser(),
                )
        except WebSocketDisconnect:
            logger.info("Browser Realtime WebSocket disconnected")
        except Exception:
            logger.exception("Browser Realtime bridge error")
            try:
                await self._send_browser({"type": "error", "message": "Voice connection failed."})
            except Exception:
                pass
        finally:
            await self._on_ended()

    async def _wait_for_start(self) -> None:
        """First browser message must be ``start`` with session metadata."""
        import time

        raw = await self._browser_ws.receive_text()
        msg = json.loads(raw)
        if msg.get("type") != "start":
            raise RuntimeError("Expected start message from browser")

        self._conversation_id = msg.get("conversation_id")
        ctx_data = msg.get("call_context") or {}
        try:
            self._call_ctx = CallContextDTO.model_validate(ctx_data)
        except Exception:
            sid = f"browser-{self._conversation_id or 'anon'}"
            self._call_ctx = CallContextDTO(call_sid=sid, from_number="+13125550000")
        self._started_at = time.time()

    async def _configure_session(self) -> None:
        assert self._openai_ws is not None
        await self._openai_ws.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "type": "realtime",
                        "model": self._settings.openai.realtime_model,
                        "instructions": SYSTEM_PROMPT,
                        "output_modalities": ["audio"],
                        "tools": self._tools.realtime_specs(),
                        "tool_choice": "auto",
                        "audio": {
                            "input": {
                                "format": {"type": "audio/pcm", "rate": SAMPLE_RATE},
                                # No whisper input transcription — avoids extra OpenAI STT cost.
                                # Assistant speech transcripts still arrive on the Realtime stream
                                # (same response) and are saved locally in call_ctx.
                                "turn_detection": {
                                    "type": "server_vad",
                                    "threshold": 0.6,
                                    "prefix_padding_ms": 250,
                                    "silence_duration_ms": 650,
                                },
                            },
                            "output": {
                                "format": {"type": "audio/pcm", "rate": SAMPLE_RATE},
                                "voice": self._settings.openai.tts_voice,
                            },
                        },
                    },
                }
            )
        )

    async def _send_initial_greeting(self) -> None:
        assert self._openai_ws is not None
        await self._openai_ws.send(
            json.dumps(
                {
                    "type": "response.create",
                    "response": {
                        "output_modalities": ["audio"],
                        "instructions": (
                            f'Say exactly this in a warm, professional tone: "{REALTIME_GREETING}"'
                        ),
                    },
                }
            )
        )

    async def _pump_browser_to_openai(self) -> None:
        assert self._openai_ws is not None
        while not self._closed:
            try:
                raw = await self._browser_ws.receive_text()
            except WebSocketDisconnect:
                break
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            mtype = msg.get("type")
            if mtype == "audio":
                audio = msg.get("audio")
                if audio:
                    await self._openai_ws.send(
                        json.dumps({"type": "input_audio_buffer.append", "audio": audio})
                    )
            elif mtype == "cancel":
                try:
                    await self._openai_ws.send(json.dumps({"type": "response.cancel"}))
                except Exception:
                    pass
            elif mtype == "end":
                self._closed = True
                try:
                    await self._openai_ws.close()
                except Exception:
                    pass
                break

    async def _pump_openai_to_browser(self) -> None:
        assert self._openai_ws is not None
        async for raw in self._openai_ws:
            if self._closed:
                break
            event = json.loads(raw)
            etype = event.get("type")

            if etype in ("response.output_audio.delta", "response.audio.delta"):
                await self._send_browser(
                    {"type": "audio", "audio": event.get("delta", "")}
                )

            elif etype == "input_audio_buffer.speech_started":
                await self._send_browser({"type": "user_speech_started"})
                # Cancel in-flight agent audio on barge-in
                try:
                    await self._openai_ws.send(json.dumps({"type": "response.cancel"}))
                except Exception:
                    pass

            elif etype == "input_audio_buffer.speech_stopped":
                await self._send_browser({"type": "user_speech_stopped"})

            elif etype in (
                "response.output_audio_transcript.done",
                "response.audio_transcript.done",
            ):
                # Free side-channel of the same Realtime response (not Whisper).
                # Persist for history; do not require a separate UI transcript flow.
                transcript = (event.get("transcript") or "").strip()
                if transcript and self._call_ctx:
                    self._call_ctx.add_turn("agent", transcript)

            elif etype == "conversation.item.input_audio_transcription.completed":
                # Ignored — input Whisper transcription is disabled.
                pass

            elif etype in ("response.created",):
                await self._send_browser({"type": "agent_speaking"})

            elif etype in ("response.done", "response.output_audio.done", "response.audio.done"):
                await self._send_browser({"type": "agent_done"})

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
                err = event.get("error") or {}
                msg = err.get("message") if isinstance(err, dict) else str(err)
                # response.cancel while idle is noisy — ignore benign cancels
                if "cancel" in (msg or "").lower() and "no active" in (msg or "").lower():
                    continue
                logger.warning("Realtime error | {}", err)
                await self._send_browser(
                    {"type": "error", "message": msg or "Realtime error"}
                )

    async def _handle_tool_call(self, event: Dict[str, Any]) -> None:
        assert self._openai_ws is not None
        assert self._call_ctx is not None
        call_id = event.get("call_id") or event.get("item_id")
        name = event.get("name") or self._pending_calls.get(call_id, {}).get("name", "")
        args_raw = event.get("arguments") or self._pending_calls.get(call_id, {}).get("args", "{}")
        self._pending_calls.pop(call_id, None)

        try:
            args = json.loads(args_raw or "{}")
        except json.JSONDecodeError:
            args = {}

        async with db_manager.session() as session:
            tool_ctx = ToolContext(session=session, call=self._call_ctx)
            try:
                result = await self._tools.invoke(name, args, tool_ctx)
            except KeyError:
                result = {"status": "error", "message": f"Unknown tool {name!r}."}
            except Exception as exc:
                logger.exception("Tool execution failed | name={}", name)
                result = {"status": "error", "message": str(exc)}

        await self._openai_ws.send(
            json.dumps(
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(result, default=str),
                    },
                }
            )
        )
        await self._openai_ws.send(json.dumps({"type": "response.create"}))

    async def _send_browser(self, payload: Dict[str, Any]) -> None:
        if self._closed:
            return
        try:
            await self._browser_ws.send_json(payload)
        except Exception:
            self._closed = True

    async def _on_ended(self) -> None:
        if self._closed:
            return
        self._closed = True
        import time

        duration = max(1, int(time.time() - self._started_at)) if self._started_at else None
        try:
            if self._call_ctx is not None:
                await aria_svc.persist_session(
                    self._call_ctx.model_dump(mode="json"),
                    conversation_id=self._conversation_id,
                    duration_seconds=duration,
                )
        except Exception:
            logger.exception("Failed to persist browser Realtime session")
        try:
            await self._send_browser({"type": "ended"})
        except Exception:
            pass
