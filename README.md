# Voice AI - Home Appliance Diagnostic Agent

End-to-end voice AI that handles inbound calls from customers whose home
appliances are malfunctioning. The agent diagnoses the issue
conversationally, walks the caller through troubleshooting, schedules a
technician when needed, and (optionally) emails the caller a unique
upload link so a photo can be analysed by GPT-4o Vision.

Built around a **Twilio Voice ↔ OpenAI Realtime API** WebSocket bridge,
with the **OpenAI Agents SDK** providing the diagnostic agent's tool set.

---

## Table of contents

1. [Architecture](#architecture)
2. [Layered design](#layered-design)
3. [Quick start (Docker)](#quick-start-docker)
4. [Local dev (no Docker)](#local-dev-no-docker)
5. [Exposing to Twilio](#exposing-to-twilio)
6. [Environment variables](#environment-variables)
7. [Conversation flow](#conversation-flow)
8. [Agent tools](#agent-tools)
9. [Database schema](#database-schema)
10. [Database flow](#database-flow)
11. [HTTP / WebSocket API](#http--websocket-api)
12. [Project layout](#project-layout)
13. [Verification](#verification)
14. [Troubleshooting](#troubleshooting)

---

## Architecture

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
                                                    ├─ SchedulingService ──▶ Postgres
                                                    ├─ UploadService     ──▶ Postgres + disk
                                                    ├─ EmailService      ──▶ SMTP
                                                    └─ VisionService     ──▶ GPT-4o (Vision)
```

The same `ToolRegistry` is reused by:

- the **Realtime API bridge** (voice mode) - tool specs are sent in the
  `session.update` event, function-call events are validated and dispatched
  to handlers, and the result is shipped back as `function_call_output`;
- the **OpenAI Agents SDK** `Agent` (text mode) - used for tests, CLI smoke
  runs, and any future web-chat surface.

Both paths share identical tool names and Pydantic input schemas, so the
behaviour is consistent across surfaces.

### Voice stack - unified speech-to-speech

We use OpenAI's **Realtime API** (`gpt-4o-realtime-preview`) as a single
audio-in / audio-out endpoint. A conventional STT → LLM → TTS pipeline
still runs - it just runs *inside* the model - giving us **sub-second turn
latency**, native tool calling, and one vendor to operate instead of three.

If finer-grained control is needed later (different STT vendor, custom
voice cloning, on-prem TTS), [`realtime_bridge.py`](app/services/realtime_bridge.py)
is the single seam to split - swap the Realtime WebSocket for a discrete
STT → LLM → TTS cascade without touching the agent, tools, or routes.

### Voice transport - two interchangeable options

There are **two** audio transports wired into this codebase, both
exercising the identical agent / prompt / tools / DB layer:

| Transport | Path | Status | Used for |
|---|---|---|---|
| **Twilio Voice + Media Streams** | `app/routes/voice.py` + [`realtime_bridge.py`](app/services/realtime_bridge.py) | Implemented | Production / phone calls |
| **Mac mic + speaker** | [`scripts/mic_voice.py`](scripts/mic_voice.py) | Implemented | Local dev + demos without telephony |

Both transports speak the same OpenAI Realtime API session protocol,
register the same tool set, and write to the same Postgres tables - only
the audio source/sink differs. Switching between them is a configuration
change, not a code change: no agent, prompt, tool, or schema code differs
between the phone path and the local path.

To run locally without telephony, use `python -m scripts.mic_voice` - your
Mac mic becomes the caller, your speaker becomes the phone earpiece.
Everything else (diagnosis, scheduling, image upload, vision analysis) is
identical to the phone path.

---

## Layered design

| Layer | Path | Responsibility |
|-------|------|----------------|
| Config | [`app/config/`](app/config/) | Singleton Pydantic Settings + loguru logging |
| Models | [`app/models/`](app/models/) | SQLAlchemy 2.0 ORM declarations |
| DTOs | [`app/dto/`](app/dto/) | Pydantic schemas for inbound/outbound contracts |
| Repositories | [`app/repositories/`](app/repositories/) | Async data-access - one repo per aggregate |
| Services | [`app/services/`](app/services/) | Business logic - scheduling, vision, email, upload, voice, realtime bridge |
| Agents | [`app/agents/`](app/agents/) | OpenAI Agents SDK agent + tool registry + prompts |
| Routes | [`app/routes/`](app/routes/) | FastAPI HTTP/WebSocket endpoints |
| Utils | [`app/utils/`](app/utils/) | Pure helpers - tokens, normalization, audio codec |
| Scripts | [`scripts/`](scripts/) | Operational scripts (seed, etc.) |

### Key design choices

- **Single source of truth for configuration.** Everything reads from
  [`get_settings()`](app/config/settings.py), an `@lru_cache(maxsize=1)`
  singleton over an aggregated `Settings` Pydantic model. Sub-domains
  (`AppSettings`, `DatabaseSettings`, `OpenAISettings`, `TwilioSettings`,
  `EmailSettings`, `UploadSettings`, `BusinessSettings`) keep concerns
  separated.
- **Pydantic everywhere there's a contract.** DTOs in `app/dto/`, agent
  tool inputs in `app/agents/schemas.py`, settings in `app/config/`.
- **Repositories own SQL.** Services orchestrate, repositories execute
  queries - no raw SQL leaks out of `app/repositories/`.
- **Agent tools defined once.** [`tool_registry.py`](app/agents/tool_registry.py)
  is the single source of tool metadata; `tools.py` holds the async
  handlers. The Agents-SDK wrappers in `diagnostic_agent.py` simply
  forward to those same handlers using `name_override` so the tool names
  match the system prompt verbatim.
- **No business logic in routes.** Routes parse the request, hand off to
  a service, and serialise the response.

---

## Quick start (Docker)

```bash
cp .env.example .env
# fill in OPENAI_API_KEY, TWILIO_*, SMTP_*, APP_PUBLIC_URL

docker compose up --build
```

What the compose pipeline does:

1. Starts Postgres 16 with a healthcheck.
2. Builds the Python 3.12 image from [`Dockerfile`](Dockerfile).
3. Calls `init_db()` on app boot - creates all 8 tables with the right
   FKs, cascades, and indexes.
4. Runs `python -m scripts.seed` to seed 7 technicians + ~280 open slots.
5. Starts Uvicorn on `:8000`.

The app waits for `db: service_healthy` before booting, so the seed and
API can rely on the database being up.

### Resetting the schema after a model change

Because we use `Base.metadata.create_all` (not Alembic) for first-boot
bootstrap, you have two ways to apply a schema change:

```bash
# Option A - wipe Docker volume and let init_db rebuild on next up
docker compose down -v
docker compose up --build

# Option B - drop and recreate just the project tables, keep the volume
python -m scripts.reset_db          # drops all tables, then init_db()
python -m scripts.seed              # re-populates technicians + slots
```

[`scripts/reset_db.py`](scripts/reset_db.py) is the destructive
counterpart of `init_db()` - useful while iterating on the data model.

---

## Local dev (no Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env
# For SQLite (no Postgres needed):
#   DATABASE_URL=sqlite+aiosqlite:///./data/voice_ai.db
mkdir -p data uploads

python -m scripts.seed              # idempotent
uvicorn app.main:app --reload
```

Visit <http://localhost:8000/health> - should return `{"status":"ok"}`.
Visit <http://localhost:8000/docs> for the auto-generated Swagger UI.

---

## Exposing to Twilio

Twilio needs a public HTTPS endpoint to hit your `/voice/inbound` webhook
and to open the Media Streams WebSocket. Use [ngrok](https://ngrok.com)
or any TCP tunnel:

```bash
ngrok http 8000
# https://<your-subdomain>.ngrok-free.app
```

Then in `.env` set:

```
APP_PUBLIC_URL=https://<your-subdomain>.ngrok-free.app
```

In the Twilio console, configure your phone number's *A CALL COMES IN*
webhook to:

```
POST  https://<your-subdomain>.ngrok-free.app/voice/inbound
```

The TwiML response opens a Media Stream WebSocket back to
`wss://<your-host>/ws/voice`, which `RealtimeBridge` proxies to the
OpenAI Realtime API. Audio in both directions stays in `g711_ulaw` (μ-law
8 kHz) end-to-end - no resampling required.

### Prefer to run locally? Use the mic script

If you'd rather iterate quickly without telephony,
[`scripts/mic_voice.py`](scripts/mic_voice.py) gives you the same agent
over your Mac's mic + speaker — no phone, no ngrok needed for the voice
path itself.

```bash
brew install portaudio                  # one-time, macOS
pip install -r requirements.txt         # pulls sounddevice + numpy
python -m scripts.mic_voice             # speak into your mic
```

Same prompt, same tools, same DB writes — only the audio transport
differs. ngrok + uvicorn are still required if you want the **emailed
upload links** to work (the customer's browser hits `/upload/{token}`
through the public URL). Wear headphones to avoid the speaker echoing
into the mic.

---

## Environment variables

See [`.env.example`](./.env.example). Every value is loaded once via
`app.config.settings.get_settings()` (LRU-cached singleton) and routed
to consumers from there - no module reads `os.environ` directly.

Grouped settings:

| Group | Keys |
|-------|------|
| App | `APP_NAME`, `APP_ENV`, `APP_HOST`, `APP_PORT`, `APP_PUBLIC_URL`, `LOG_LEVEL` |
| Database | `DATABASE_URL`, `DATABASE_ECHO` |
| OpenAI | `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_REALTIME_MODEL`, `OPENAI_VISION_MODEL`, `OPENAI_TTS_VOICE` |
| Twilio | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` |
| SMTP | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME`, `SMTP_USE_TLS` |
| Upload | `UPLOAD_DIR`, `UPLOAD_LINK_TTL_HOURS`, `UPLOAD_MAX_BYTES` |
| Business | `BUSINESS_TIMEZONE`, `SUPPORTED_APPLIANCES` |

---

## Conversation flow

Driven by the system prompt in [`app/agents/prompts.py`](app/agents/prompts.py):

1. **Greet** the caller and introduce Aria, the diagnostic assistant.
2. **Identify** the appliance (washer, dryer, refrigerator, dishwasher,
   oven, HVAC, microwave, …).
3. **Collect symptoms**: problem description, when it started, error
   codes, sounds, observed behaviours, recent changes - one focused
   question at a time.
4. Call **`record_diagnosis`** to lock in the working hypothesis.
5. Walk the caller through 2–4 **safe troubleshooting steps**.
6. If unresolved or hazardous → call **`find_available_slots`**
   (zip + appliance), read 2–3 options aloud, the caller picks → call
   **`book_appointment`** → read back the confirmation (technician,
   date, time, code).
7. (Optional) If a photo would help → call **`request_image_upload`**.
   The caller gets an emailed link; the upload is auto-analysed by
   GPT-4o Vision and the summary is stored on the `UploadLink` row.

Throughout the call, the agent calls **`update_call_context`** to keep
the in-memory `CallContextDTO` in sync, so it never re-asks for
information the caller has already given.

### Safety hand-off

The system prompt explicitly instructs the agent to short-circuit on gas
smells, sparks, smoke, or flooding - recommending the caller stop using
the appliance and shut off power/gas/water at the source if safe, then
prioritise an emergency technician visit.

---

## Agent tools

Tools are declared **once** in
[`app/agents/tool_registry.py`](app/agents/tool_registry.py). The same
registry feeds both the Realtime API bridge and the OpenAI Agents SDK.

| Tool | Pydantic input | Behaviour |
|------|----------------|-----------|
| `update_call_context` | `UpdateCallContextInput` | Persist learned facts (name, ZIP, email, appliance, symptoms, error codes) into the per-call `CallContextDTO` |
| `record_diagnosis` | `RecordDiagnosisInput` | Lock in the working diagnosis + severity |
| `find_available_slots` | `FindSlotsInput` | Match technicians by ZIP + appliance, return open availability slots |
| `book_appointment` | `BookAppointmentInput` | Create the appointment, mark slot booked, return confirmation code |
| `request_image_upload` | `RequestImageUploadInput` | Generate a unique upload token, email the customer a time-limited link |

Each handler runs inside a `ToolContext(session, call)`:

- `session` is the request-scoped `AsyncSession` from `DatabaseManager`,
  so transactions are bound to the unit of work.
- `call` is the active `CallContextDTO` from `CallSessionStore` (an
  in-memory singleton keyed by Twilio `CallSid`).

---

## Database schema

Created automatically on app startup via `init_db()`. See
[`app/models/`](app/models/) for the source of truth, and the [Database
flow](#database-flow) section below for how rows come into being.

### Entity diagram

```
                  ┌─────────────┐
                  │  customers  │  PK id, UNIQUE phone
                  │  (id, name, │
                  │   phone,    │
                  │   email,    │
                  │   default_  │
                  │   address,  │
                  │   default_  │
                  │   zip)      │
                  └──────┬──────┘
       1:N  RESTRICT     │     1:N  RESTRICT
   ┌────────────┬────────┼────────┬────────────┐
   │            │        │        │            │
   ▼            ▼        ▼        ▼            ▼
 (1:N        (1:N    (1:N      (RESTRICT, indexed by customer_id)
  RESTRICT)   RESTR.) RESTR.)
┌──────────┐ ┌─────────────┐ ┌──────────────┐
│appointmts│ │ call_records│ │ upload_links │
└────┬─────┘ └──────┬──────┘ └──────────────┘
     │              │ N:1 SET NULL
     │              ▼
     │       ┌────────────┐
     │  N:1  │appointments│   ← call_records.appointment_id
     │ RESTR.│            │
     ▼       └────────────┘
┌────────────┐
│ technicians│  PK id, UNIQUE employee_code
└────┬───────┘
     │ 1:N  CASCADE on delete   1:N  RESTRICT
     ├──────────────┬──────────────┬──────────────┐
     ▼              ▼              ▼              ▼
service_areas  specialties  availabilities  appointments
   (CASCADE)    (CASCADE)     (CASCADE)      (RESTRICT)
                                  ▲
                                  │ N:1  SET NULL
                                  │
                              appointments.availability_id
```

### Tables

| Table | Key columns | FKs | Notes |
|---|---|---|---|
| `customers` | `id`, **UNIQUE `phone`** | - | Identified by E.164 phone. Email/name optional (we may not have them yet) |
| `technicians` | `id`, **UNIQUE `employee_code`**, **UNIQUE `email`** | - | `is_active` for soft enable/disable |
| `service_areas` | `id` | `technician_id → technicians (CASCADE)` | UNIQUE `(technician_id, zip_code)`, indexed by both |
| `specialties` | `id` | `technician_id → technicians (CASCADE)` | UNIQUE `(technician_id, appliance_type)` |
| `availabilities` | `id` | `technician_id → technicians (CASCADE)` | UNIQUE `(technician_id, start_at)` so we can't double-book a slot |
| `appointments` | `id`, **UNIQUE `confirmation_code`** | `customer_id → customers (RESTRICT)`, `technician_id → technicians (RESTRICT)`, `availability_id → availabilities (SET NULL)` | `service_address` / `service_zip` are a snapshot of where the tech actually goes (may differ from customer's defaults) |
| `call_records` | `id`, **UNIQUE `call_sid`** | `customer_id → customers (RESTRICT, NULL OK)`, `appointment_id → appointments (SET NULL, NULL OK)` | One row per inbound call - persisted at hangup |
| `upload_links` | `id`, **UNIQUE `token`** | `customer_id → customers (RESTRICT)` | `call_sid` is a *string lookup helper*, not a FK (CallRecord may not exist yet when the link is issued) |

### Cascade rules at a glance

| If you delete… | …this happens to children |
|---|---|
| a **customer** | `RESTRICT` everywhere - blocks the delete if they have appointments / calls / upload links. Protects history. |
| a **technician** | `service_areas`, `specialties`, `availabilities` `CASCADE`. `appointments` `RESTRICT` so historical bookings survive. |
| an **availability** | `appointments.availability_id` set to `NULL`. The appointment row survives - only the link to the slot is severed. |
| an **appointment** | `call_records.appointment_id` set to `NULL`. The call row survives. |

`passive_deletes=True` is set on all `relationship()` declarations so
SQLAlchemy lets the DB enforce these rules instead of emitting cascading
DELETEs from Python.

### Sample data (seed)

[`scripts/seed.py`](scripts/seed.py) inserts:

- 7 technicians across 12 ZIP codes in the 60601–60630 range
- 2–4 appliance specialties per technician
- 4 slots/day × ~10 weekdays = ~40 slots per technician (~280 total open slots)

`customers`, `appointments`, `call_records`, and `upload_links` are
seeded *empty* - they get populated through the live flow described
below. The seed is idempotent (safe to re-run).

---

## Database flow

Here's how rows come into being and link up over the lifetime of a call.

### 1. Service catalogue (seed time, static)

```
seed.py  ─▶  technicians ─┬─▶ service_areas (zip codes served)
                          ├─▶ specialties   (appliances handled)
                          └─▶ availabilities (open time slots)
```

These four tables are the "supply side" - what we have to offer
customers. They're populated once and updated only when an operations
person changes a tech's coverage or schedule.

### 2. Customer calls in (call start)

```
Twilio → /voice/inbound
  └─▶  CallSessionStore.create(call_sid, from_number)   # in-memory only
```

At this point the **DB is not touched**. The agent is gathering facts
into `CallContextDTO`; we don't know who the caller is yet, and we don't
want a half-empty `call_records` row on every spam call.

### 3. Agent collects information (mid-call)

```
agent → update_call_context(name, zip, email, …)
  └─▶  CallSessionStore.get(call_sid).update(…)        # still in-memory

agent → record_diagnosis(severity, causes, summary)
  └─▶  CallSessionStore.get(call_sid).diagnosis_summary = …
```

The agent calls `update_call_context` and `record_diagnosis` repeatedly
during the conversation. Both are **memory-only** mutations on the
`CallContextDTO` - fast, with zero DB load on chatty turns. This is also
how we satisfy the "don't repeat questions" behaviour.

### 4. First DB write - booking an appointment

```
agent → find_available_slots(zip, appliance)
  └─▶  TechnicianRepository.find_for_zip_and_appliance(…)   ── SELECT
       AppointmentRepository.find_open_slots(tech_ids, …)   ── SELECT

agent → book_appointment(name, phone, zip, appliance, slot_id)
  ├─▶  CustomerRepository.upsert(phone, …)
  │      ├─ found? update missing fields                   ── UPDATE
  │      └─ not found? insert new customer                 ── INSERT
  ├─▶  Appointment(customer_id=…, technician_id=…,
  │                availability_id=…, …)                   ── INSERT
  └─▶  Availability.is_booked = True                       ── UPDATE
       (so the slot disappears from future find_open_slots)
```

The first time we touch the DB on the write path is when the customer
agrees to a booking. The customer is **upserted by phone** - that's the
natural key. A repeat caller from the same number doesn't create a
duplicate `customers` row; instead, missing fields (e.g. an email we
didn't have before) are filled in.

### 5. Optional - image upload request

```
agent → request_image_upload(email)
  ├─▶  CustomerRepository.upsert(phone, email, …)         ── INSERT or UPDATE
  ├─▶  UploadLink(customer_id=…, token=…, expires_at=…,
  │               call_sid=current_call)                  ── INSERT
  └─▶  EmailService.send(upload_url)                      ── SMTP
```

If the agent already booked an appointment in step 4, the customer
already exists - `upsert` finds them and just attaches the upload link.

### 6. Customer uploads a photo (out-of-band, post-call)

```
GET /upload/{token}     ─▶  UploadLinkRepository.get_by_token(…)  ── SELECT
                            (renders the form)

POST /upload/{token}    ─▶  store file under uploads/{token}/…
                            UploadLink.status = UPLOADED          ── UPDATE
                            BackgroundTask:
                              VisionService.analyze_image(path)   ── GPT-4o
                              UploadLink.analysis_summary = …
                              UploadLink.status = ANALYZED        ── UPDATE
```

This happens minutes or hours after the call ends. The link is bound to
the customer via `customer_id`, so even though the call is long over,
the analysis is still attributable.

### 7. Caller hangs up - finalize the call record

```
RealtimeBridge._on_call_ended:
  ├─▶  CallRecord (already exists?  return - idempotent)
  ├─▶  CustomerRepository.upsert(phone, name, email, …)   ── UPSERT (if known)
  └─▶  CallRecord(call_sid=…,
                  customer_id=upserted.id (or NULL),
                  appointment_id=ctx.booked_appointment_id (or NULL),
                  transcript=…, diagnosis_summary=…,
                  outcome="appointment_booked"|"image_requested"|
                          "self_resolved"|"dropped")      ── INSERT
```

Only when the call is over do we materialize the `CallRecord` row - one
write per call, with FKs filled in based on what actually happened:

- **Booked an appointment?** `customer_id` is set, `appointment_id`
  points to the booked row.
- **Asked for a photo but didn't book?** `customer_id` is set,
  `appointment_id` is `NULL`.
- **Customer self-resolved with troubleshooting?** Same - customer
  identified, no appointment.
- **Spam / dropped call?** `customer_id` and `appointment_id` are both
  `NULL`. We still log it for analytics but don't pollute `customers`.

### Reading the data afterwards

Every interesting question has a single-join answer:

| Question | SQL (sketch) |
|---|---|
| Did this call lead to a booking? | `JOIN appointments ON call_records.appointment_id = appointments.id` |
| Show all calls for one customer | `WHERE call_records.customer_id = ?` |
| Show all photos for one customer | `WHERE upload_links.customer_id = ?` |
| Which technicians are overbooked next week? | `JOIN appointments` then `GROUP BY technician_id` |
| Repeat-caller rate | `customers` rows with `COUNT(call_records) > 1` |

---

## HTTP / WebSocket API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Service info |
| GET | `/health` | Liveness probe |
| POST | `/voice/inbound` | Twilio voice webhook (returns TwiML) |
| WS | `/ws/voice` | Twilio Media Stream → OpenAI Realtime bridge |
| GET | `/upload/{token}` | Customer-facing upload form |
| POST | `/upload/{token}` | Multipart upload; queues GPT-4o Vision analysis |
| GET | `/docs` | Auto-generated OpenAPI / Swagger UI |

---

## Project layout

```
app/
  __init__.py
  main.py                       # FastAPI factory + lifespan
  config/
    settings.py                 # singleton Pydantic Settings
    logging_config.py           # loguru + stdlib bridge
  models/                       # SQLAlchemy ORM
    base.py                     #   Base + TimestampMixin
    customer.py                 #   Customer  (UNIQUE phone)
    technician.py               #   Technician
    service_area.py             #   ServiceArea  (FK → technician, CASCADE)
    specialty.py                #   Specialty    (FK → technician, CASCADE)
    availability.py             #   Availability (FK → technician, CASCADE)
    appointment.py              #   Appointment  (FKs → customer, technician,
                                #                       availability)
    upload_link.py              #   UploadLink   (FK → customer)
    call_record.py              #   CallRecord   (FKs → customer, appointment)
  dto/                          # Pydantic DTOs (customer, technician,
                                #   appointment, diagnosis, call, upload)
  repositories/                 # async data access (BaseRepository + 5 repos
                                #   incl. CustomerRepository.upsert)
  services/
    scheduling_service.py       # match technicians + upsert customer + book
    vision_service.py           # GPT-4o Vision JSON analysis
    email_service.py            # aiosmtplib delivery
    upload_service.py           # upsert customer + token issuance + storage
    voice_service.py            # Twilio TwiML builder
    realtime_bridge.py          # Twilio Media Streams ↔ Realtime API +
                                #   call-end CallRecord persistence
    call_session_store.py       # in-memory per-call state singleton
    openai_client.py            # AsyncOpenAI factory singleton
  agents/
    prompts.py                  # SYSTEM_PROMPT + REALTIME_GREETING
    schemas.py                  # tool input Pydantic models
    tool_registry.py            # ToolRegistry + ToolDefinition
    tools.py                    # async handlers + ToolContext
    diagnostic_agent.py         # OpenAI Agents SDK wrapper
  routes/                       # health, voice, upload
  database/
    session.py                  # DatabaseManager singleton + init_db
  utils/
    helpers.py                  # tokens, normalization, time
    audio.py                    # μ-law / PCM16 codec helpers
scripts/
  seed.py                       # idempotent seed (technicians + slots)
  reset_db.py                   # drop + recreate all project tables
docker-compose.yml
Dockerfile
requirements.txt
.env.example
```

---

## Verification

The system is verified end-to-end:

```bash
# 1. Imports resolve cleanly
python -c "from app.main import app; print(app.title)"
# → Voice Diagnostic Agent

# 2. Both surfaces expose the same tool names
python -c "
from app.agents.diagnostic_agent import DiagnosticAgentFactory
from app.agents.tool_registry import build_tool_registry
print([t.name for t in DiagnosticAgentFactory().build_agent().tools])
print([d.name for d in build_tool_registry().all()])
"
# → ['update_call_context', 'record_diagnosis', 'find_available_slots',
#    'book_appointment', 'request_image_upload']  (both lines identical)

# 3. Schema reset + seed round-trip
mkdir -p data
DATABASE_URL='sqlite+aiosqlite:///./data/voice_ai.db' python -m scripts.reset_db
DATABASE_URL='sqlite+aiosqlite:///./data/voice_ai.db' python -m scripts.seed
# → all 8 tables created, 7 technicians, 280 slots inserted

# 4. Customer-upsert verification (same phone → single customers row)
DATABASE_URL='sqlite+aiosqlite:///./data/voice_ai.db' python -c "
import asyncio
from app.database.session import db_manager
from app.services.scheduling_service import SchedulingService
from app.services.upload_service import UploadService
from app.dto.appointment import AppointmentCreateDTO

async def main():
    async with db_manager.session() as s:
        svc = SchedulingService(s)
        slots = await svc.find_available_slots('60601', 'washer', 1)
        appt1 = await svc.book_appointment(AppointmentCreateDTO(
            customer_name='Jane Doe', customer_phone='+13125551234',
            customer_email='jane@example.com', service_zip='60601',
            appliance_type='washer', issue_summary='Wont spin',
            availability_id=slots[0].availability_id))
        # Same phone, different appliance - should reuse customer.
        slots = await svc.find_available_slots('60601', 'dryer', 1)
        appt2 = await svc.book_appointment(AppointmentCreateDTO(
            customer_name='Jane Doe', customer_phone='+13125551234',
            service_zip='60601', appliance_type='dryer',
            issue_summary='Wont start',
            availability_id=slots[0].availability_id))
        assert appt1.customer_id == appt2.customer_id
        print(f'OK - both bookings share customer_id={appt1.customer_id}')

asyncio.run(main())
"
# → OK - both bookings share customer_id=1
```

Driving the agent without a phone (text mode):

```python
import asyncio
from app.agents.diagnostic_agent import diagnostic_agent_factory
from app.agents.tools import ToolContext
from app.dto.call import CallContextDTO
from app.database.session import db_manager

async def main():
    async with db_manager.session() as session:
        ctx = ToolContext(session=session, call=CallContextDTO(call_sid="test-001"))
        reply = await diagnostic_agent_factory.run_text(
            "Hi, my dryer in 60601 stopped heating yesterday.", ctx,
        )
        print(reply)

asyncio.run(main())
```

---

## Troubleshooting

### `audioop` ModuleNotFoundError on Python 3.13

The `audioop` standard-library module was removed in Python 3.13.
`requirements.txt` already pulls in `audioop-lts` for Python ≥ 3.13;
make sure your venv was rebuilt after the requirements update.

### `email-validator is not installed`

Pydantic's `EmailStr` requires the optional dependency. It's already
listed (`pydantic[email]` + `email-validator`); ensure
`pip install -r requirements.txt` ran in your active venv.

### `ResolutionImpossible: openai-agents → openai>=1.66.5`

Old pin clash. The current `requirements.txt` uses ranges
(`openai>=1.66.5,<2`, `openai-agents>=0.0.17,<0.3`) that resolve cleanly
with a recent pip - pip resolves to roughly `openai 1.109` +
`openai-agents 0.2.x`.

### Twilio "11200 HTTP retrieval failure"

Your `APP_PUBLIC_URL` isn't reachable from the public internet. Use
ngrok (or similar), and ensure the URL in `.env` matches the one
configured in the Twilio console for your phone number.

### "Database is locked" on SQLite

SQLite isn't great for concurrent writes - fine for local development,
but prefer the Postgres docker-compose stack for any meaningful traffic.

### `docker compose up` fails with `input/output error` on a blob or `metadata_v2.db`

Docker Desktop's local content store / BuildKit metadata is corrupted
(common after force-quits or low-disk events on Mac). Try in order:

```bash
df -h /                                   # check free space first
docker builder prune -a -f                # clear BuildKit cache
docker system prune -a --volumes -f       # heavier cleanup
```

If that doesn't help: Docker Desktop → **Settings → Troubleshoot →
Clean / Purge data** (keeps Docker installed) or **Reset to factory
defaults** (nuclear). Then `docker compose up --build` will re-pull
images cleanly.

In the meantime, the SQLite path under [Local dev](#local-dev-no-docker)
runs the entire system without Docker.

### Schema looks stale after a model change

The app uses `init_db()` (`Base.metadata.create_all`) for first-boot
bootstrap, which **does not alter existing tables**. After editing
anything in `app/models/`:

```bash
# Postgres: drop everything and rebuild
python -m scripts.reset_db
python -m scripts.seed

# Docker Postgres: nuke the volume and let init_db recreate on next up
docker compose down -v
docker compose up --build
```

For non-destructive migrations in production, swap `init_db()` for
Alembic (already in `requirements.txt`).

---

## License

MIT License — free to use, modify, and distribute.
