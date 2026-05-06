from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr


class CustomerDTO(BaseModel):
    id: int
    name: Optional[str] = None
    phone: str
    email: Optional[EmailStr] = None
    default_address: Optional[str] = None
    default_zip: Optional[str] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class CustomerUpsertDTO(BaseModel):
    phone: str
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    default_address: Optional[str] = None
    default_zip: Optional[str] = None
