"""Audio codec helpers for the Twilio <-> OpenAI Realtime bridge.

Twilio Media Streams send and expect μ-law (G.711) at 8 kHz.
OpenAI Realtime accepts μ-law (`g711_ulaw`) directly when configured,
so most of the time we just shuttle base64 frames unchanged. These helpers
exist for cases where we need PCM16 conversion or to centralise base64
encoding logic.
"""
from __future__ import annotations

import audioop
import base64


def mulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
    """Convert μ-law 8 kHz to PCM16 8 kHz."""
    return audioop.ulaw2lin(mulaw_bytes, 2)


def pcm16_to_mulaw(pcm_bytes: bytes) -> bytes:
    """Convert PCM16 to μ-law."""
    return audioop.lin2ulaw(pcm_bytes, 2)


def b64encode_audio(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def b64decode_audio(payload: str) -> bytes:
    return base64.b64decode(payload)
