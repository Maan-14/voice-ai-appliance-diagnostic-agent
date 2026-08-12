# ARIA — AI Home Appliance Diagnostic Agent

ARIA is a conversational AI agent that helps customers diagnose home appliance
problems, troubleshoot them safely, and book a technician when needed.

Talk to ARIA naturally through **text**, **browser voice**, or a **phone call**.
ARIA can understand symptoms, reason through possible causes, guide customers
through safe troubleshooting, schedule technicians, and request photos for
AI-powered visual analysis.

```
┌──────────────────────────────────────────────────────────────┐
│                         ARIA                                 │
│          AI Home Appliance Diagnostic Agent                  │
│                                                              │
│     Text Chat     Voice     Phone                            │
│                         │                                    │
│                         ▼                                    │
│                 Diagnostic Agent                             │
│                         │                                    │
│       ┌─────────┬───────┼────────┬──────────┐               │
│       ▼         ▼       ▼        ▼          ▼               │
│   Diagnosis  Troubleshoot  Booking  Image AI  History       │
└──────────────────────────────────────────────────────────────┘
```

---

## What ARIA can do

- **Text chat** — ChatGPT-style conversational diagnosis
- **Voice conversations** — hands-free, natural voice interaction in the browser
- **Phone support** — Twilio-powered inbound calls
- **Troubleshooting** — guided, appliance-specific diagnostics
- **Technician scheduling** — finds and books available technicians
- **Visual diagnosis** — customers can upload appliance photos for AI analysis
- **Conversation history** — stores transcripts, diagnoses, and outcomes
- **Shared agent logic** — text, browser voice, and phone calls use the same diagnostic tools and backend

---

## Try ARIA

```bash
git clone https://github.com/Maan-14/voice-ai-appliance-diagnostic-agent.git
cd voice-ai-appliance-diagnostic-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and set your `OPENAI_API_KEY`.

```bash
mkdir -p data uploads
python -m scripts.seed
uvicorn app.main:app --reload
```

Open [http://localhost:8000](http://localhost:8000)

Choose **Chat with ARIA** for a text conversation or **Talk to ARIA** for a
hands-free voice session.

---

## Example conversation

**Customer**

> My dryer turns on but the clothes are still wet after a full cycle.

**ARIA**

> Got it. Does the dryer feel warm while it’s running, or does it stay completely cold?

**Customer**

> It stays cold.

**ARIA**

> That helps narrow it down. The heating system may not be working. Before we
> schedule a technician, let’s check a couple of safe things…

Then ARIA continues through diagnosis and, if needed, books a visit:

```
✓ Appliance identified: Dryer
✓ Symptoms collected
✓ Diagnosis recorded
✓ Troubleshooting attempted
✓ Technician appointment booked
```

---

## Why ARIA?

ARIA isn’t just an LLM chat interface. The agent is connected to real
application services and tools.

The model can:

- reason about the customer’s symptoms
- maintain conversation context
- call validated backend tools
- query technician availability
- book appointments
- generate upload links
- trigger image analysis
- persist conversation outcomes

**Design principle:** the LLM handles conversation and reasoning;
deterministic backend services handle business operations.

---

## Talk to ARIA

The product UI is served by FastAPI from [`web/`](web/).

| Mode | What you get |
|------|----------------|
| **Chat with ARIA** | Streaming text chat with conversation history |
| **Talk to ARIA** | Hands-free browser voice with live captions |
| **Phone** | Inbound Twilio call → Realtime speech bridge |

### Voice interfaces

| Interface | Pipeline |
|-----------|----------|
| Browser voice | Microphone → STT → Diagnostic Agent → TTS |
| Phone | Twilio Media Streams → OpenAI Realtime API → Diagnostic Agent |

Both use the same diagnostic tools, business services, and database.

---

## Architecture

```
 Text / Browser Voice / Phone
              │
              ▼
        Diagnostic Agent
   (same tools + same schemas)
              │
    ┌─────────┼─────────┬──────────┐
    ▼         ▼         ▼          ▼
 Scheduling  Upload   Vision    Persistence
```

- Tools are defined **once** and shared across every surface
- Routes stay thin — services own business logic
- Repositories own SQL — no raw queries in routes or UI code

For deeper detail, see [Architecture](docs/architecture.md),
[Agent & Tools](docs/agent-tools.md), [Voice](docs/voice.md), and
[Database](docs/database.md).

---

## Agent & tools

| Tool | Purpose |
|------|---------|
| `update_call_context` | Remember facts the customer already shared |
| `record_diagnosis` | Lock in the working diagnosis |
| `find_available_slots` | Find technicians by ZIP + appliance |
| `book_appointment` | Book a slot and return a confirmation |
| `request_image_upload` | Email a secure photo upload link |

Full tool contracts and conversation flow:
[docs/agent-tools.md](docs/agent-tools.md)

---

## Data & persistence

```
PostgreSQL / SQLite
        │
        ├── Customers
        ├── Technicians
        ├── Appointments
        ├── Call Records
        ├── Conversations (web text + voice)
        └── Upload Links
```

Customer records are upserted by phone number. Appointments link to
technicians and availability slots. Web and phone conversations can be
persisted with transcript, diagnosis, and outcome.

Schema details: [docs/database.md](docs/database.md)

---

## Configuration

Copy [`.env.example`](.env.example) to `.env` and set:

| Required | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | LLM, STT, TTS, vision, titles |

Other keys (Twilio, SMTP, public URL) are only needed for phone calls and
photo-email delivery. See [docs/development.md](docs/development.md).

---

## Project structure

```
app/                 FastAPI backend, agent, tools, services, DB
web/                 Product UI (landing, chat, voice)
scripts/             seed, chat REPL, mic demo
docs/                Engineering documentation
tests/               Automated tests
```

---

## Verification

```bash
pytest
python -c "from app.main import app; print(app.title)"
```

---

## Documentation

| Doc | Contents |
|-----|----------|
| [Architecture](docs/architecture.md) | Layers, design rules, API surface |
| [Agent & Tools](docs/agent-tools.md) | Prompt flow, tool registry, safety |
| [Voice](docs/voice.md) | Browser vs phone voice pipelines |
| [Database](docs/database.md) | Schema, cascades, write flow |
| [Development](docs/development.md) | Docker, Twilio, troubleshooting |

---

## License

MIT License — free to use, modify, and distribute.
