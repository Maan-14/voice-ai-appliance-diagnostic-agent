from app.dto.customer import CustomerDTO, CustomerUpsertDTO
from app.dto.technician import TechnicianDTO, TechnicianCreateDTO
from app.dto.appointment import (
    AppointmentDTO,
    AppointmentCreateDTO,
    AvailabilitySlotDTO,
)
from app.dto.diagnosis import (
    ApplianceSymptomsDTO,
    DiagnosticStepDTO,
    DiagnosticReportDTO,
    VisionAnalysisDTO,
)
from app.dto.call import CallContextDTO, CallStartDTO
from app.dto.upload import UploadLinkDTO, UploadResultDTO

__all__ = [
    "CustomerDTO",
    "CustomerUpsertDTO",
    "TechnicianDTO",
    "TechnicianCreateDTO",
    "AppointmentDTO",
    "AppointmentCreateDTO",
    "AvailabilitySlotDTO",
    "ApplianceSymptomsDTO",
    "DiagnosticStepDTO",
    "DiagnosticReportDTO",
    "VisionAnalysisDTO",
    "CallContextDTO",
    "CallStartDTO",
    "UploadLinkDTO",
    "UploadResultDTO",
]
