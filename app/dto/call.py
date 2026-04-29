from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


class CallStartDTO(BaseModel):
    call_sid: str
    from_number: Optional[str] = None
    to_number: Optional[str] = None


class CallContextDTO(BaseModel):
    """In-memory state per active call — passed into agent tools as context."""

    call_sid: str
    from_number: Optional[str] = None

    customer_name: Optional[str] = None
    customer_zip: Optional[str] = None
    customer_email: Optional[EmailStr] = None
    customer_address: Optional[str] = None

    appliance_type: Optional[str] = None
    symptoms: List[str] = Field(default_factory=list)
    error_codes: List[str] = Field(default_factory=list)
    diagnosis_summary: Optional[str] = None

    transcript_lines: List[str] = Field(default_factory=list)
    outcome: Optional[str] = None  # "self_resolved" | "appointment_booked" | "image_requested"

    # Set by handle_book_appointment so the bridge can link CallRecord -> Appointment.
    booked_appointment_id: Optional[int] = None

    def add_turn(self, role: str, text: str) -> None:
        self.transcript_lines.append(f"{role}: {text}")
