---
name: aria-appliance-diagnostic
description: >
  End-to-end playbook for the Aria voice AI home-appliance diagnostic agent —
  inbound Twilio calls, OpenAI Realtime bridge, diagnosis tools, technician
  booking, and tokenized photo upload with vision analysis. Apply for any work
  across this codebase.
---

# Aria — home appliance diagnostic agent

Aria handles inbound calls from customers whose appliances are failing. She
diagnoses conversationally, walks through troubleshooting, books a technician
when needed, and can email a unique upload link so a photo can be analysed by
GPT-4o Vision.

Stack: FastAPI + async SQLAlchemy + Postgres (SQLite for local). Voice path is
Twilio Media Streams bridged to the OpenAI Realtime API (speech-to-speech). The
same tool set also powers the text agent used by `scripts/chat.py`.

## End-to-end call flow

```
Customer phone
  → Twilio Voice
  → POST /voice/inbound  (TwiML <Connect><Stream>)
  → wss /ws/voice
  → RealtimeBridge (app/services/realtime_bridge.py)
       audio both ways, barge-in, transcript, tool dispatch, persist on hangup
  → OpenAI Realtime API
       function_call → ToolRegistry → handlers (app/agents/tools.py)
                    → services → repositories → DB
```

Local equivalents (same agent / tools / DB, different audio transport):

- Text: `python -m scripts.chat`
- Mic + speaker: `python -m scripts.mic_voice`

## Conversation capabilities

1. Collect caller context (name, ZIP, appliance, symptoms, error codes).
2. Diagnose and optionally record a working diagnosis.
3. Find available slots and book an appointment.
4. Email a photo-upload link after the caller confirms their address aloud;
   Vision analyses the image when uploaded.

Tools are defined once in `app/agents/tool_registry.py` and mirrored in
`app/agents/diagnostic_agent.py`. Both surfaces must expose the identical set.

## Layering

```
routes → services → repositories → models
```

- Routes parse HTTP/WebSocket only — no business logic.
- Services orchestrate (scheduling, email, upload, vision, voice bridge).
- Repositories own all SQL.
- Config via `get_settings()` only — do not read `os.environ` elsewhere.
- Per-call state lives in `call_session_store` (keyed by CallSid) and is written
  to `call_records` on hangup.
- Request DB sessions use `Depends(get_session)`; the bridge and background work
  open their own via `db_manager.session()`.

## Email safety (do not weaken)

Highest-risk failure: inventing a customer email from their name and mailing a
stranger. Three layers must stay intact:

1. Prompt protocol — ask → read back letter-by-letter → confirm aloud.
2. Schema validators — reject placeholder domains (`_reject_placeholder_email`).
3. Runtime gates in `handle_request_image_upload` — `customer_confirmed_aloud`
   plus `_looks_name_derived()` before any SMTP / upload-link side effect.

## Operational notes

- `.env` is loaded once at import; restart after changing env vars.
- `requirements.txt` pins `openai<2` because the Realtime bridge targets the
  1.x event shape.
- Tool handlers return JSON-serialisable dicts (`status` key); values go
  straight back as `function_call_output`.
- Schema boot is `create_all` — Alembic is present but not configured yet.
- Lint with `ruff check`; avoid wholesale `ruff format` rewrites unless asked.

## Commands

```bash
uvicorn app.main:app --reload     # http://localhost:8000/health  ·  /docs
python -m scripts.seed            # 7 technicians + open slots
python -m scripts.chat            # text-mode agent
python -m scripts.mic_voice       # local voice demo
docker compose up --build         # Postgres 16 + app
```
