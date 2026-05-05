"""Pydantic input schemas for the diagnostic agent's tools.

These are the canonical contracts between the LLM and our backend.
We expose their JSON schema directly to the Realtime API and to the
OpenAI Agents SDK.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# RFC 2606 reserved test/placeholder domains, plus a few common
# fabrications we've seen the model produce.
_PLACEHOLDER_EMAIL_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "test.com",
    "test.org",
    "domain.com",
    "email.com",
    "mail.com",
}
_PLACEHOLDER_TLDS = {"example", "test", "invalid", "localhost"}


def _reject_placeholder_email(value: str) -> str:
    """Block obvious model-fabricated emails before they reach SMTP."""
    domain = value.split("@", 1)[-1].lower().strip()
    tld = domain.rsplit(".", 1)[-1] if "." in domain else domain
    if domain in _PLACEHOLDER_EMAIL_DOMAINS or tld in _PLACEHOLDER_TLDS:
        raise ValueError(
            f"{value!r} looks like a placeholder address (domain {domain!r}). "
            "Ask the customer to spell out their real email and try again."
        )
    return value


class UpdateCallContextInput(BaseModel):
    """Persist newly-learned facts about the caller / appliance."""

    customer_name: Optional[str] = Field(default=None, description="Caller's full name.")
    customer_zip: Optional[str] = Field(
        default=None, description="5-digit US ZIP code where the appliance is located."
    )
    customer_email: Optional[EmailStr] = Field(
        default=None,
        description=(
            "Caller's real email, captured verbatim. Do not invent or construct "
            "from the caller's name. Placeholder domains will be rejected."
        ),
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

    @field_validator("customer_email")
    @classmethod
    def _reject_placeholder(cls, v: Optional[str]) -> Optional[str]:
        return _reject_placeholder_email(v) if v else v


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
    customer_email: Optional[EmailStr] = Field(
        default=None,
        description=(
            "Optional. If provided, must be the customer's real email — "
            "never fabricated or constructed from their name."
        ),
    )
    service_address: Optional[str] = None
    appliance_type: str
    issue_summary: str
    availability_id: int

    @field_validator("customer_email")
    @classmethod
    def _reject_placeholder(cls, v: Optional[str]) -> Optional[str]:
        return _reject_placeholder_email(v) if v else v


class RequestImageUploadInput(BaseModel):
    customer_email: EmailStr = Field(
        ...,
        description=(
            "The customer's real email, captured verbatim from the call. "
            "MUST NOT be invented or constructed from the customer's name. "
            "Placeholder domains (example.com, test.com, etc.) will be rejected."
        ),
    )
    appliance_type: Optional[str] = None
    notes: Optional[str] = Field(
        default=None,
        description="Any extra context about what we want to see in the photo.",
    )

    @field_validator("customer_email")
    @classmethod
    def _reject_placeholder(cls, v: str) -> str:
        return _reject_placeholder_email(v)
