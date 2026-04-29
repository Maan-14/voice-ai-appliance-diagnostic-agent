from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.appointment import AppointmentStatus


class AvailabilitySlotDTO(BaseModel):
    availability_id: int
    technician_id: int
    technician_name: str
    start_at: datetime
    end_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppointmentCreateDTO(BaseModel):
    """Booking request — the agent provides these fields, the service does the rest."""

    customer_name: str = Field(..., min_length=1, max_length=120)
    customer_phone: str
    customer_email: Optional[EmailStr] = None
    customer_address: Optional[str] = None
    service_zip: str
    appliance_type: str
    issue_summary: str
    availability_id: int


class AppointmentDTO(BaseModel):
    id: int
    customer_id: int
    customer_name: Optional[str] = None
    customer_phone: str
    customer_email: Optional[EmailStr] = None
    service_address: Optional[str] = None
    service_zip: str
    appliance_type: str
    issue_summary: str
    technician_id: int
    technician_name: Optional[str] = None
    scheduled_start: datetime
    scheduled_end: datetime
    status: AppointmentStatus
    confirmation_code: str

    model_config = ConfigDict(from_attributes=True)
