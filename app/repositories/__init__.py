from app.repositories.base import BaseRepository
from app.repositories.customer_repo import CustomerRepository
from app.repositories.technician_repo import TechnicianRepository
from app.repositories.appointment_repo import AppointmentRepository
from app.repositories.upload_repo import UploadLinkRepository
from app.repositories.call_repo import CallRecordRepository

__all__ = [
    "BaseRepository",
    "CustomerRepository",
    "TechnicianRepository",
    "AppointmentRepository",
    "UploadLinkRepository",
    "CallRecordRepository",
]
