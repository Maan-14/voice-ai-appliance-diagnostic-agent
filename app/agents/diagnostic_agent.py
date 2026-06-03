"""OpenAI Agents SDK wrapper around the diagnostic tool registry.

The voice path uses the Realtime API directly (see app.services.realtime_bridge),
but we also expose an Agents-SDK-based ``Agent`` for text channels (testing,
CLI, future web chat). Both paths reuse the same handler functions so behavior
stays consistent.
"""
from __future__ import annotations

from typing import Any, Dict

from agents import Agent, RunContextWrapper, Runner, function_tool

from app.agents.prompts import SYSTEM_PROMPT
from app.agents.schemas import (
    BookAppointmentInput,
    FindSlotsInput,
    RecordDiagnosisInput,
    RequestImageUploadInput,
    UpdateCallContextInput,
)
from app.agents.tools import (
    ToolContext,
    handle_book_appointment,
    handle_find_slots,
    handle_record_diagnosis,
    handle_request_image_upload,
    handle_update_call_context,
)
from app.config.settings import get_settings


# --- function_tool wrappers -------------------------------------------------
#
# The Agents SDK passes the run context wrapper as the first argument when a
# tool function declares it. We forward to our shared async handlers.


@function_tool(name_override="update_call_context")
async def update_call_context_tool(
    ctx: RunContextWrapper[ToolContext], args: UpdateCallContextInput
) -> Dict[str, Any]:
    """Persist newly-learned facts about the caller and appliance."""
    return await handle_update_call_context(args, ctx.context)


@function_tool(name_override="record_diagnosis")
async def record_diagnosis_tool(
    ctx: RunContextWrapper[ToolContext], args: RecordDiagnosisInput
) -> Dict[str, Any]:
    """Lock in the working diagnosis."""
    return await handle_record_diagnosis(args, ctx.context)


@function_tool(name_override="find_available_slots")
async def find_slots_tool(
    ctx: RunContextWrapper[ToolContext], args: FindSlotsInput
) -> Dict[str, Any]:
    """Find available technician appointment slots."""
    return await handle_find_slots(args, ctx.context)


@function_tool(name_override="book_appointment")
async def book_appointment_tool(
    ctx: RunContextWrapper[ToolContext], args: BookAppointmentInput
) -> Dict[str, Any]:
    """Book an appointment from a chosen availability slot."""
    return await handle_book_appointment(args, ctx.context)


@function_tool(name_override="request_image_upload")
async def request_image_upload_tool(
    ctx: RunContextWrapper[ToolContext], args: RequestImageUploadInput
) -> Dict[str, Any]:
    """Email the caller a unique image upload link."""
    return await handle_request_image_upload(args, ctx.context)


class DiagnosticAgentFactory:
    """Builds a fresh Agent instance bound to the active call's context.

    Singleton-ish: model + prompt come from settings, but the actual ``Agent``
    is constructed per-run so each call gets its own context binding.
    """

    _instance: "DiagnosticAgentFactory | None" = None

    def __new__(cls) -> "DiagnosticAgentFactory":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def build_agent(self) -> Agent[ToolContext]:
        return Agent[ToolContext](
            name="Aria — Diagnostic Agent",
            instructions=SYSTEM_PROMPT,
            model=get_settings().openai.model,
            tools=[
                update_call_context_tool,
                record_diagnosis_tool,
                find_slots_tool,
                book_appointment_tool,
                request_image_upload_tool,
            ],
        )

    async def run_text(self, user_input: str, ctx: ToolContext) -> str:
        """Convenience: run the agent in text mode and return the final reply."""
        agent = self.build_agent()
        result = await Runner.run(agent, user_input, context=ctx)
        return result.final_output  # type: ignore[no-any-return]


diagnostic_agent_factory = DiagnosticAgentFactory()
