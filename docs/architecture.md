# Architecture

ARIA’s backend is a layered FastAPI application. The product UI lives in
[`web/`](../web/) and is served from the same process.

## High-level flow

```
 Customer phone
       │
       ▼
   Twilio Voice ───▶  POST /voice/inbound  ──▶  TwiML <Connect><Stream …>
       │
       ▼  (Media Streams, μ-law / 8 kHz, base64)
   wss://…/ws/voice  ◀──▶  RealtimeBridge  ◀──▶  OpenAI Realtime API
                                │                       │
                                │                       ▼
                                │              function_call events
                                ▼
                         ToolRegistry  ──▶  Pydantic-validated handlers
                                                    │
                                                    ├─ SchedulingService
                                                    ├─ UploadService
                                                    ├─ EmailService
                                                    └─ VisionService
```

Browser text and browser voice go through `/api/aria/*` and the OpenAI
Agents SDK path. Phone audio goes through the Realtime bridge. Both reuse
the same tool names, Pydantic schemas, and handlers.

## Layers

| Layer | Path | Responsibility |
|-------|------|----------------|
| Config | `app/config/` | Singleton Pydantic Settings + logging |
| Models | `app/models/` | SQLAlchemy ORM |
| DTOs | `app/dto/` | Request/response contracts |
| Repositories | `app/repositories/` | Async SQL only |
| Services | `app/services/` | Business logic |
| Agents | `app/agents/` | Prompt, tool registry, Agents SDK wrapper |
| Routes | `app/routes/` | HTTP / WebSocket adapters |
| Web UI | `web/` | Product SPA |

## Design rules

- **Single settings entry.** Everything reads `get_settings()` — an
  `@lru_cache(maxsize=1)` singleton. Modules do not read `os.environ`
  directly.
- **Pydantic at every contract.** Settings, DTOs, and tool inputs are
  validated models.
- **Repositories own SQL.** Services orchestrate; raw SQL stays in
  `app/repositories/`.
- **Tools defined once.** `tool_registry.py` is the source of tool
  metadata; `tools.py` holds handlers. Agents SDK wrappers forward to
  those handlers with matching `name_override` names.
- **No business logic in routes.** Routes parse, call a service, return.

## HTTP / WebSocket API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Product UI |
| GET | `/static/…` | SPA assets |
| GET | `/health` | Liveness |
| POST | `/api/aria/session` | Start web session |
| POST | `/api/aria/chat/stream` | Streamed agent turn (SSE) |
| POST | `/api/aria/chat` | Non-streaming agent turn |
| POST | `/api/aria/transcribe` | Whisper STT |
| POST | `/api/aria/speak` | TTS |
| POST | `/api/aria/session/persist` | Finalize session |
| GET | `/api/aria/conversations` | Conversation history |
| GET | `/api/aria/ops` | Operations summary |
| GET | `/api/aria/status` | Integration flags |
| POST | `/voice/inbound` | Twilio webhook |
| WS | `/ws/voice` | Twilio ↔ Realtime bridge |
| GET/POST | `/upload/{token}` | Photo upload + vision analysis |
| GET | `/docs` | OpenAPI |

## Project layout

```
app/
  main.py                 FastAPI factory + serves web/
  config/                 settings + logging
  models/                 ORM
  dto/                    Pydantic DTOs
  repositories/           data access
  services/               scheduling, vision, email, upload, realtime, web
  agents/                 prompts, schemas, registry, handlers, Agents SDK
  routes/                 health, voice, upload, aria
  database/               engine + sessions
  utils/                  helpers + audio codec
web/                      product SPA
scripts/                  seed, reset_db, chat, mic_voice
tests/
```
