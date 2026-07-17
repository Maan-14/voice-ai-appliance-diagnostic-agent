# CLAUDE.md

Project guidance for Claude Code. Keep answers and changes consistent with the
conventions below — they are deliberate.

## What this project is

Voice AI agent ("Aria") for home-appliance diagnostics. Inbound Twilio calls are
bridged to the OpenAI Realtime API (speech-to-speech); the agent diagnoses the
issue, books technicians, and can email a tokenized photo-upload link whose
image is analysed by GPT-4o Vision. FastAPI + async SQLAlchemy + Postgres
(SQLite fallback for local dev).

## Commands

```bash
make install        # pip install -r requirements.txt
make run            # uvicorn with reload (http://localhost:8000)
make seed           # idempotent: 7 technicians + 14 days of slots
make test           # pytest
make lint           # ruff check app scripts tests
make fmt            # ruff format (opt-in; not enforced in CI)
make docker-up      # Postgres 16 + app via docker compose
make chat           # text-mode agent REPL (no telephony needed)
python -m scripts.mic_voice   # voice demo using local mic (needs portaudio)
```

## Architecture (read this before touching call flow)

```
Twilio call → POST /voice/inbound (TwiML) → wss /ws/voice
    → app/services/realtime_bridge.py  (THE core file: audio pump both ways,
      barge-in, transcript capture, tool dispatch, persistence on hangup)
    → app/agents/tool_registry.py      (single source of tool definitions)
    → app/agents/tools.py              (handlers) → services → repositories → DB
```

Layering is strict: routes → services → repositories → models. Raw SQL lives
only in `app/repositories/`. Routes contain no business logic.

Key invariants:

- **Tools are defined once** in `tool_registry.py` (name + description +
  Pydantic schema + handler). Both surfaces — the Realtime voice bridge and the
  Agents-SDK text agent (`diagnostic_agent.py`, used by `scripts/chat.py`) —
  consume the same registry/handlers. Never add a tool to one surface only.
- **Settings** come from `get_settings()` (`app/config/settings.py`), an
  lru_cached singleton. Don't read `os.environ` directly.
- **Per-call state** lives in the in-memory `call_session_store` keyed by
  Twilio CallSid; it is persisted to `call_records` only on hangup.
- **DB sessions**: request-scoped via `Depends(get_session)`; background tasks
  and the bridge open their own via `db_manager.session()`.

## Email anti-hallucination guards (do not weaken)

The highest-risk failure mode is the LLM inventing a customer email from their
name and mailing a stranger. Three intentional layers exist:

1. Prompt protocol in `app/agents/prompts.py` (ask → read back → confirm).
2. Schema validators in `app/agents/schemas.py` reject placeholder domains.
3. Runtime gates in `handle_request_image_upload` (`app/agents/tools.py`):
   `customer_confirmed_aloud` flag + `_looks_name_derived()` heuristic.

## Gotchas

- `DATABASE_URL` defaults to SQLite (`./data/voice_ai.db`); docker-compose
  overrides it to Postgres. Schema is `create_all` on boot — no migrations yet
  (Alembic is installed but unconfigured).
- `.env` is loaded once at import time in `settings.py`; changing env vars
  requires a restart.
- Tool handlers must return JSON-serialisable dicts — their return value goes
  straight back to the model as `function_call_output`.
- `requirements.txt` caps `openai<2` on purpose: the Realtime bridge targets
  the 1.x event shape.
- Formatting: `ruff format` is available but the repo predates it — don't
  reformat files wholesale; CI enforces `ruff check` only.
