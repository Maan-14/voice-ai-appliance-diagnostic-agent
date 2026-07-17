---
name: add-agent-tool
description: >
  Add, rename, or remove a tool (function call) for the diagnostic agent.
  Use whenever the agent needs a new capability — e.g. "add a cancel_appointment
  tool" or "let the agent send an SMS confirmation". A tool touches four files
  in lockstep; missing one silently breaks voice/text parity.
---

# Adding a tool to the diagnostic agent

Tools are defined ONCE and consumed by two surfaces: the Realtime voice bridge
(`realtime_bridge.py`) and the Agents-SDK text agent (`diagnostic_agent.py`).
Both must always expose the identical tool set. Follow the steps in order.

## Step 1 — Input schema (`app/agents/schemas.py`)

Define a `<Name>Input(BaseModel)`. Rules:

- Field `description=` strings are the LLM's documentation — write them for the
  model, stating what may NOT be invented (see existing schemas for tone).
- Any email field MUST reuse the `_reject_placeholder_email` validator.
- Prefer `Optional` fields with safe fallbacks over required fields the model
  might fabricate under pressure (see `BookAppointmentInput.customer_phone`,
  which falls back to caller-ID).

## Step 2 — Handler (`app/agents/tools.py`)

```python
async def handle_<name>(args: <Name>Input, ctx: ToolContext) -> Dict[str, Any]:
```

- Return a JSON-serialisable dict with a `"status"` key ("ok" / "error" /
  domain-specific like "needs_confirmation"). The dict goes verbatim to the
  model as `function_call_output` — no ORM objects, no raw `datetime`
  (use `.model_dump(mode="json")` or `.isoformat()`).
- Expected domain failures → return `{"status": "error", "message": ...}` so
  the model can recover conversationally. Only let unexpected exceptions
  propagate (the bridge catches and stringifies them).
- Real logic lives in a service (`app/services/`); the handler validates,
  delegates via `ctx.session`, and updates `ctx.call` state (e.g. `outcome`).
- Guard-rail checks (confirmation gates, heuristics) go FIRST, before any DB
  or network side effect — see `handle_request_image_upload`.

## Step 3 — Registry (`app/agents/tool_registry.py`)

Add a `ToolDefinition` in `build_tool_registry()`:

- `name`: snake_case; this exact string is what the model calls.
- `description`: tells the model WHEN to call it, not how it's implemented.
- Never hand-write JSON specs — `ToolDefinition` derives both the Realtime
  (flat) and chat-completions (nested) formats from the Pydantic schema.

## Step 4 — SDK wrapper (`app/agents/diagnostic_agent.py`)

Add a `@function_tool(name_override="<name>")` wrapper forwarding to the same
handler, and append it to the `tools=[...]` list in `build_agent()`.
`name_override` MUST match the registry name character-for-character.

## Step 5 — Prompt (`app/agents/prompts.py`) — only if needed

If the conversation flow should reference the tool, mention it by exact name
in backticks. If the tool has a confirmation protocol, document the protocol
in the prompt AND enforce it in the handler (prompt-only guards get ignored
under pressure; see the email protocol as the model to copy).

## Step 6 — Test and verify

1. Unit-test the handler's guard/short-circuit paths when you add tests
   (pure paths need no DB — pass `session=None`, a `CallContextDTO`, and
   `asyncio.run(...)`).
2. Lint the touched files: `ruff check app/agents`
3. Parity check — both surfaces see the tool:
   ```bash
   python -c "
   from app.agents.tool_registry import build_tool_registry
   names = [d.name for d in build_tool_registry().all()]
   assert '<name>' in names, names
   from app.agents.diagnostic_agent import diagnostic_agent_factory
   sdk = [t.name for t in diagnostic_agent_factory.build_agent().tools]
   assert set(names) == set(sdk), (names, sdk)
   print('parity OK:', names)"
   ```
4. Live smoke test in text mode: `python -m scripts.chat`, steer the
   conversation so the model calls the new tool, confirm the handler ran
   (check the log line).

## Removal / rename

Reverse order: prompt → SDK wrapper → registry → handler → schema, then rerun
the parity check. For a rename, grep the old name across `app/` —
the prompt references tool names verbatim.
