# Voice

ARIA supports two voice implementations. They share the same diagnostic
tools, services, and database.

## Comparison

| Interface | Pipeline | Entry |
|-----------|----------|-------|
| **Browser voice** | Mic → STT → Diagnostic Agent → TTS | `web/` → `/api/aria/*` |
| **Phone** | Twilio Media Streams → OpenAI Realtime API → tools | `/voice/inbound` + `/ws/voice` |

## Browser voice

Used by **Talk to ARIA** in the product UI:

1. Hands-free capture with simple VAD
2. Whisper transcription (`/api/aria/transcribe`)
3. Streaming agent turn (`/api/aria/chat/stream`)
4. Sentence-chunked TTS (`/api/aria/speak`) with an audio queue
5. Mic muted while ARIA is speaking (half-duplex)
6. **End conversation** hard-stops audio, queue, mic, and pending requests

Sessions persist to conversation history on end.

## Phone voice

Twilio needs a public HTTPS URL for the inbound webhook and Media Streams
WebSocket. The Realtime bridge proxies audio and dispatches the same
tool registry used by text and browser voice.

Configured Realtime model comes from settings (`OPENAI_REALTIME_MODEL`),
not from hardcoded README assumptions.

## Local Realtime mic demo

For a laptop mic demo against the Realtime path (no Twilio):

```bash
python -m scripts.mic_voice
```

Requires PortAudio on the host. Prefer headphones to avoid echo.
