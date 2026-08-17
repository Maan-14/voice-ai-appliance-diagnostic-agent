# Agent & tools

## Conversation flow

Driven by the system prompt in `app/agents/prompts.py`:

1. Greet the caller and introduce ARIA.
2. Identify the appliance.
3. Collect symptoms one focused question at a time.
4. Call `record_diagnosis` to lock in the working hypothesis.
5. Walk through 2–4 safe troubleshooting steps.
6. If unresolved → `find_available_slots` → customer picks →
   `book_appointment` → read back confirmation.
7. If a photo would help → `request_image_upload` (emailed link,
   analysed by vision).

Throughout the call, `update_call_context` keeps learned facts in sync so
ARIA does not re-ask for information already given.

## Safety hand-off

On gas smells, sparks, smoke, or flooding, the prompt instructs ARIA to
stop DIY troubleshooting, advise shutting off power/gas/water if safe,
and prioritise an emergency visit.

## Tool registry

Tools are declared once in `app/agents/tool_registry.py` and reused by:

- the Realtime bridge (phone)
- the OpenAI Agents SDK agent (web text + browser voice)

| Tool | Input model | Behaviour |
|------|-------------|-----------|
| `update_call_context` | `UpdateCallContextInput` | Persist learned facts into `CallContextDTO` |
| `record_diagnosis` | `RecordDiagnosisInput` | Lock diagnosis + severity |
| `find_available_slots` | `FindSlotsInput` | Match technicians by ZIP + appliance |
| `book_appointment` | `BookAppointmentInput` | Create appointment, mark slot booked |
| `request_image_upload` | `RequestImageUploadInput` | Issue token + email upload link |

Handlers run inside `ToolContext(session, call)`:

- `session` — request-scoped async DB session
- `call` — active `CallContextDTO` (in-memory for the live call/session)

Business operations go through `SchedulingService`, `UploadService`,
`EmailService`, and `VisionService` — not duplicated in the UI.
