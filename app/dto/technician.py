from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TechnicianCreateDTO(BaseModel):
    name: str
    email: EmailStr
    phone: str
    employee_code: str
    employment_type: str = "full_time"
    zip_codes: List[str] = Field(default_factory=list)
    appliance_specialties: List[str] = Field(default_factory=list)


class TechnicianDTO(BaseModel):
    id: int
    name: str
    email: EmailStr
    phone: str
    employee_code: str
    employment_type: str
    is_active: bool
    zip_codes: List[str] = Field(default_factory=list)
    appliance_specialties: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
