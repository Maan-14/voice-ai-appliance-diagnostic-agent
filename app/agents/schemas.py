"""Pydantic input schemas for the diagnostic agent's tools.

These are the canonical contracts between the LLM and our backend.
We expose their JSON schema directly to the Realtime API and to the
OpenAI Agents SDK.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


class UpdateCallContextInput(BaseModel):
    """Persist newly-learned facts about the caller / appliance."""

    customer_name: Optional[str] = Field(default=None, description="Caller's full name.")
    customer_zip: Optional[str] = Field(
        default=None, description="5-digit US ZIP code where the appliance is located."
    )
    customer_email: Optional[EmailStr] = Field(
        default=None, description="Caller's email address."
    )
    customer_address: Optional[str] = Field(
        default=None, description="Service address (street + city)."
    )
    appliance_type: Optional[str] = Field(
        default=None, description="One of: washer, dryer, refrigerator, dishwasher, oven, hvac, microwave."
    )
    symptoms: Optional[List[str]] = Field(
        default=None, description="Symptoms or observed behaviors collected so far."
    )
    error_codes: Optional[List[str]] = Field(
        default=None, description="Error codes shown on the appliance display."
    )


class RecordDiagnosisInput(BaseModel):
    """Lock in the agent's working diagnosis."""

    appliance_type: str
    likely_causes: List[str]
    severity: str = Field(
        default="medium",
        description="low | medium | high | critical",
    )
    diagnosis_summary: str = Field(
        ..., description="One- or two-sentence summary of the most probable problem."
    )


class FindSlotsInput(BaseModel):
    zip_code: str = Field(..., description="5-digit US ZIP code.")
    appliance_type: str
    max_slots: int = Field(default=4, ge=1, le=10)


class BookAppointmentInput(BaseModel):
    customer_name: str
    customer_phone: Optional[str] = Field(
        default=None,
        description="If omitted, will fall back to the call's caller-ID.",
    )
    service_zip: str = Field(..., description="ZIP where the technician will go.")
    customer_email: Optional[EmailStr] = None
    service_address: Optional[str] = None
    appliance_type: str
    issue_summary: str
    availability_id: int


class RequestImageUploadInput(BaseModel):
    customer_email: EmailStr
    appliance_type: Optional[str] = None
    notes: Optional[str] = Field(
        default=None,
        description="Any extra context about what we want to see in the photo.",
    )
