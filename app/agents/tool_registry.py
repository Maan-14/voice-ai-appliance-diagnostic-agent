"""Single source of tool definitions for the diagnostic agent.

A `ToolDefinition` couples:
- a stable name and human-readable description (what the LLM sees),
- a Pydantic input schema (validated args),
- an async handler (what executes when the tool is called).

The registry is consumed by:
- the OpenAI Agents SDK ``Agent`` (text-mode), and
- the Realtime API bridge (voice-mode), which forwards JSON tool specs
  via the ``session.update`` event.

Keeping tools in one place avoids drift between the two surfaces.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Type

from pydantic import BaseModel

from app.agents.schemas import (
    BookAppointmentInput,
    FindSlotsInput,
    RecordDiagnosisInput,
    RequestImageUploadInput,
    UpdateCallContextInput,
)
from app.agents.tools import (
    handle_book_appointment,
    handle_find_slots,
    handle_record_diagnosis,
    handle_request_image_upload,
    handle_update_call_context,
)


ToolHandler = Callable[[BaseModel, "ToolContext"], Awaitable[Dict[str, Any]]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: Type[BaseModel]
    handler: ToolHandler

    def realtime_spec(self) -> Dict[str, Any]:
        """Tool specification in OpenAI Realtime API format."""
        schema = self.input_schema.model_json_schema()
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": schema,
        }

    def openai_tool_spec(self) -> Dict[str, Any]:
        """Tool spec for chat completions / Responses API."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema.model_json_schema(),
            },
        }


# `ToolContext` is forward-referenced in ToolHandler — defined in tools.py to
# avoid a circular import at type-eval time.
from app.agents.tools import ToolContext  # noqa: E402  (after dataclass to break cycle)


class ToolRegistry:
    def __init__(self, definitions: List[ToolDefinition]) -> None:
        self._by_name: Dict[str, ToolDefinition] = {d.name: d for d in definitions}

    def all(self) -> List[ToolDefinition]:
        return list(self._by_name.values())

    def get(self, name: str) -> ToolDefinition:
        if name not in self._by_name:
            raise KeyError(f"Unknown tool: {name}")
        return self._by_name[name]

    def realtime_specs(self) -> List[Dict[str, Any]]:
        return [d.realtime_spec() for d in self._by_name.values()]

    def openai_specs(self) -> List[Dict[str, Any]]:
        return [d.openai_tool_spec() for d in self._by_name.values()]

    async def invoke(
        self, name: str, raw_args: Dict[str, Any], context: ToolContext
    ) -> Dict[str, Any]:
        defn = self.get(name)
        validated = defn.input_schema.model_validate(raw_args)
        return await defn.handler(validated, context)


def build_tool_registry() -> ToolRegistry:
    """Construct the registry of all diagnostic-agent tools."""
    return ToolRegistry(
        [
            ToolDefinition(
                name="update_call_context",
                description=(
                    "Persist newly-learned facts about the caller and the appliance "
                    "so they are remembered for the rest of the call. Call this any "
                    "time the customer tells you their name, ZIP, email, the "
                    "appliance type, symptoms, or error codes."
                ),
                input_schema=UpdateCallContextInput,
                handler=handle_update_call_context,
            ),
            ToolDefinition(
                name="record_diagnosis",
                description=(
                    "Lock in your working diagnosis once you've gathered enough "
                    "symptom information. Use this before giving troubleshooting "
                    "steps or scheduling a technician."
                ),
                input_schema=RecordDiagnosisInput,
                handler=handle_record_diagnosis,
            ),
            ToolDefinition(
                name="find_available_slots",
                description=(
                    "Find available technician appointment slots for the customer's "
                    "ZIP code and appliance type. Returns a short list of slots "
                    "the agent can read aloud."
                ),
                input_schema=FindSlotsInput,
                handler=handle_find_slots,
            ),
            ToolDefinition(
                name="book_appointment",
                description=(
                    "Book an appointment for the customer using the availability_id "
                    "they chose from `find_available_slots`. Returns confirmation "
                    "details to read back to the customer."
                ),
                input_schema=BookAppointmentInput,
                handler=handle_book_appointment,
            ),
            ToolDefinition(
                name="request_image_upload",
                description=(
                    "Email the customer a unique, time-limited link they can use "
                    "to upload a photo of the appliance issue. Use this when a "
                    "photo would meaningfully improve the diagnosis."
                ),
                input_schema=RequestImageUploadInput,
                handler=handle_request_image_upload,
            ),
        ]
    )
