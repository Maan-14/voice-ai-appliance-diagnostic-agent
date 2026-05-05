"""Local mic + speaker voice chat with the diagnostic agent.

Skips Twilio + ngrok entirely — we open a direct WebSocket to the OpenAI
Realtime API and pipe your Mac's microphone in / speaker out. Same agent
prompt, same tool registry, same DB writes as the production phone path.

Useful for:
- Demoing the voice agent without a Twilio account.
- Iterating on prompt / tool changes with sub-second feedback.
- Validating the OpenAI Realtime path before wiring telephony.

Prereqs:
    macOS: brew install portaudio
    pip install -r requirements.txt   # pulls sounddevice + numpy

Run:
    python -m scripts.mic_voice

Tip: wear headphones. Without echo cancellation the agent will hear its
own voice through your laptop speaker and start talking over itself.
"""
from __future__ import annotations

import asyncio
import base64
import json
import sys
from collections import deque
from typing import Any, Dict, Optional

try:
    import numpy as np
    import sounddevice as sd
except ImportError as exc:  # pragma: no cover
    print(
        "✗ This script needs sounddevice + numpy + PortAudio.\n"
        "  macOS:  brew install portaudio && pip install -r requirements.txt\n"
        f"  (import failed: {exc})"
    )
    sys.exit(1)

from websockets.asyncio.client import connect as ws_connect

from app.agents.prompts import REALTIME_GREETING, SYSTEM_PROMPT
from app.agents.tool_registry import build_tool_registry
from app.agents.tools import ToolContext
from app.config.logging_config import configure_logging, get_logger
from app.config.settings import get_settings
from app.database.session import db_manager, dispose_db
from app.dto.call import CallContextDTO

configure_logging()
logger = get_logger("mic_voice")


# OpenAI Realtime accepts pcm16 @ 24 kHz mono natively — no resampling needed.
SAMPLE_RATE = 24_000
CHANNELS = 1
BLOCK_MS = 50
BLOCK_FRAMES = SAMPLE_RATE * BLOCK_MS // 1000
SAMPLE_BYTES = 2  # int16

REALTIME_URL_TMPL = "wss://api.openai.com/v1/realtime?model={model}"


class MicVoiceClient:
    """Single-session client: mic ⇄ OpenAI Realtime ⇄ speaker."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._tools = build_tool_registry()
        self._ws: Optional[Any] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self._mic_queue: asyncio.Queue[bytes] = asyncio.Queue()
        # speaker_buffer is a deque of bytes — the speaker callback drains it.
        self._speaker_buffer: deque[bytes] = deque()
        self._pending_calls: Dict[str, Dict[str, str]] = {}

        self._call_ctx = CallContextDTO(
            call_sid="mic-local",
            from_number="+13125550000",  # fake caller-ID for tool handlers
        )

    # ------------------------------------------------------------------
    # Audio device callbacks (run in PortAudio threads)
    # ------------------------------------------------------------------

    def _mic_callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            logger.warning("mic stream status: {}", status)
        # indata is int16 because we configured dtype='int16'
        pcm_bytes = bytes(indata)
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(
                self._mic_queue.put(pcm_bytes), self._loop
            )

    def _speaker_callback(self, outdata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            logger.warning("speaker stream status: {}", status)

        needed = frames * SAMPLE_BYTES
        chunk = bytearray()
        while len(chunk) < needed and self._speaker_buffer:
            chunk.extend(self._speaker_buffer.popleft())

        if len(chunk) < needed:
            chunk.extend(b"\x00" * (needed - len(chunk)))
        elif len(chunk) > needed:
            extra = bytes(chunk[needed:])
            chunk = chunk[:needed]
            self._speaker_buffer.appendleft(extra)

        outdata[:] = np.frombuffer(bytes(chunk), dtype=np.int16).reshape(-1, CHANNELS)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def run(self) -> None:
        if not self._settings.openai.api_key.startswith("sk-"):
            print("✗ OPENAI_API_KEY missing or invalid — check your .env")
            return

        self._loop = asyncio.get_running_loop()

        url = REALTIME_URL_TMPL.format(model=self._settings.openai.realtime_model)
        headers = {
            "Authorization": f"Bearer {self._settings.openai.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        print(f"🔌 Connecting to {self._settings.openai.realtime_model}…")
        async with ws_connect(url, additional_headers=headers) as ws:
            self._ws = ws
            await self._configure_session()
            print("✓ Session configured")

            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=BLOCK_FRAMES,
                callback=self._mic_callback,
            ), sd.OutputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=BLOCK_FRAMES,
                callback=self._speaker_callback,
            ):
                print("🎤 Mic + speaker live — start talking. Ctrl+C to stop.\n")
                await self._send_initial_greeting()

                send_task = asyncio.create_task(self._mic_to_openai())
                recv_task = asyncio.create_task(self._openai_to_speaker())
                try:
                    await asyncio.gather(send_task, recv_task)
                except asyncio.CancelledError:
                    pass
                finally:
                    send_task.cancel()
                    recv_task.cancel()

    # ------------------------------------------------------------------
    # OpenAI session control
    # ------------------------------------------------------------------

    async def _configure_session(self) -> None:
        assert self._ws is not None
        await self._ws.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "modalities": ["audio", "text"],
                        "instructions": SYSTEM_PROMPT,
                        "voice": self._settings.openai.tts_voice,
                        "input_audio_format": "pcm16",
                        "output_audio_format": "pcm16",
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
        assert self._ws is not None
        await self._ws.send(
            json.dumps(
                {
                    "type": "response.create",
                    "response": {
                        "modalities": ["audio", "text"],
                        "instructions": (
                            f'Say exactly this in a warm, professional tone: '
                            f'"{REALTIME_GREETING}"'
                        ),
                    },
                }
            )
        )

    # ------------------------------------------------------------------
    # Audio pumps
    # ------------------------------------------------------------------

    async def _mic_to_openai(self) -> None:
        assert self._ws is not None
        while True:
            chunk = await self._mic_queue.get()
            await self._ws.send(
                json.dumps(
                    {
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(chunk).decode("ascii"),
                    }
                )
            )

    async def _openai_to_speaker(self) -> None:
        assert self._ws is not None
        async for raw in self._ws:
            event = json.loads(raw)
            etype = event.get("type")

            if etype == "response.audio.delta":
                self._speaker_buffer.append(base64.b64decode(event["delta"]))

            elif etype == "response.audio_transcript.done":
                transcript = event.get("transcript", "")
                if transcript:
                    print(f"🤖 Aria: {transcript}")
                    self._call_ctx.add_turn("agent", transcript)

            elif etype == "conversation.item.input_audio_transcription.completed":
                transcript = event.get("transcript", "")
                if transcript:
                    print(f"🎤 You:  {transcript}")
                    self._call_ctx.add_turn("caller", transcript)

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

    # ------------------------------------------------------------------
    # Tool dispatch (same logic as the Twilio bridge)
    # ------------------------------------------------------------------

    async def _handle_tool_call(self, event: Dict[str, Any]) -> None:
        assert self._ws is not None
        call_id = event.get("call_id") or event.get("item_id")
        name = event.get("name") or self._pending_calls.get(call_id, {}).get("name", "")
        args_raw = (
            event.get("arguments")
            or self._pending_calls.get(call_id, {}).get("args", "{}")
        )
        self._pending_calls.pop(call_id, None)

        try:
            args = json.loads(args_raw or "{}")
        except json.JSONDecodeError:
            args = {}

        print(f"🔧 {name}({json.dumps(args, default=str)})")

        async with db_manager.session() as session:
            tool_ctx = ToolContext(session=session, call=self._call_ctx)
            try:
                result = await self._tools.invoke(name, args, tool_ctx)
            except KeyError:
                result = {"status": "error", "message": f"Unknown tool {name!r}."}
            except Exception as exc:
                logger.exception("Tool execution failed | name={}", name)
                result = {"status": "error", "message": str(exc)}

        # Truncate long results (e.g. slot lists) for terminal readability
        preview = json.dumps(result, default=str)
        if len(preview) > 200:
            preview = preview[:200] + "…"
        print(f"   → {preview}")

        await self._ws.send(
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
        await self._ws.send(json.dumps({"type": "response.create"}))


async def main() -> None:
    print()
    print("┌──────────────────────────────────────────────────────────────┐")
    print("│  Aria — Voice mode (Mac mic + speaker, no Twilio)            │")
    print("│  Wear headphones to avoid echo. Ctrl+C to stop.              │")
    print("└──────────────────────────────────────────────────────────────┘")

    client = MicVoiceClient()
    try:
        await client.run()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    except Exception:
        logger.exception("Fatal error")
    finally:
        await dispose_db()
        print("\n--- Final call context ---")
        print(client._call_ctx.model_dump_json(indent=2, exclude={"transcript_lines"}))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye.")
        sys.exit(0)
