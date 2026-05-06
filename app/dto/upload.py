from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.upload_link import UploadStatus


class UploadLinkDTO(BaseModel):
    id: int
    token: str
    customer_id: int
    customer_email: Optional[EmailStr] = None
    appliance_type: Optional[str] = None
    expires_at: datetime
    status: UploadStatus
    upload_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UploadResultDTO(BaseModel):
    token: str
    status: UploadStatus
    stored_path: Optional[str] = None
    analysis_summary: Optional[str] = None
