"""Tool handler implementations.

Each handler receives a validated Pydantic input and a ``ToolContext`` that
exposes the request-scoped DB session and the active call context. Handlers
return a JSON-serialisable dict that gets surfaced back to the LLM.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.logging_config import get_logger
from app.dto.appointment import AppointmentCreateDTO
from app.dto.call import CallContextDTO
from app.services.email_service import EmailService
from app.services.scheduling_service import SchedulingError, SchedulingService
from app.services.upload_service import UploadService
from app.utils.helpers import normalize_appliance, normalize_phone, normalize_zip

# These are imported lazily inside this module to keep import order clean.
from app.agents.schemas import (  # noqa: E402
    BookAppointmentInput,
    FindSlotsInput,
    RecordDiagnosisInput,
    RequestImageUploadInput,
    UpdateCallContextInput,
)

logger = get_logger(__name__)


@dataclass
class ToolContext:
    """Per-call execution context for tool handlers."""

    session: AsyncSession
    call: CallContextDTO


# ---------- update_call_context ----------

async def handle_update_call_context(
    args: UpdateCallContextInput, ctx: ToolContext
) -> Dict[str, Any]:
    if args.customer_name:
        ctx.call.customer_name = args.customer_name.strip()
    if args.customer_zip:
        ctx.call.customer_zip = normalize_zip(args.customer_zip) or args.customer_zip
    if args.customer_email:
        ctx.call.customer_email = args.customer_email
    if args.customer_address:
        ctx.call.customer_address = args.customer_address
    if args.appliance_type:
        ctx.call.appliance_type = (
            normalize_appliance(args.appliance_type) or args.appliance_type.lower()
        )
    if args.symptoms:
        for s in args.symptoms:
            if s and s not in ctx.call.symptoms:
                ctx.call.symptoms.append(s)
    if args.error_codes:
        for c in args.error_codes:
            if c and c not in ctx.call.error_codes:
                ctx.call.error_codes.append(c)

    logger.info(
        "Call context updated | sid={} appliance={} zip={}",
        ctx.call.call_sid, ctx.call.appliance_type, ctx.call.customer_zip,
    )
    return {"status": "ok", "context": ctx.call.model_dump(exclude={"transcript_lines"})}


# ---------- record_diagnosis ----------

async def handle_record_diagnosis(
    args: RecordDiagnosisInput, ctx: ToolContext
) -> Dict[str, Any]:
    ctx.call.appliance_type = (
        normalize_appliance(args.appliance_type) or args.appliance_type
    )
    ctx.call.diagnosis_summary = args.diagnosis_summary
    logger.info(
        "Diagnosis recorded | sid={} severity={} causes={}",
        ctx.call.call_sid, args.severity, args.likely_causes,
    )
    return {
        "status": "ok",
        "appliance_type": ctx.call.appliance_type,
        "severity": args.severity,
        "likely_causes": args.likely_causes,
        "diagnosis_summary": args.diagnosis_summary,
    }


# ---------- find_available_slots ----------

async def handle_find_slots(
    args: FindSlotsInput, ctx: ToolContext
) -> Dict[str, Any]:
    service = SchedulingService(ctx.session)
    try:
        slots = await service.find_available_slots(
            zip_code=args.zip_code,
            appliance_type=args.appliance_type,
            max_slots=args.max_slots,
        )
    except SchedulingError as exc:
        return {"status": "error", "message": str(exc), "slots": []}

    if not slots:
        return {
            "status": "no_match",
            "message": (
                f"No technicians currently available for {args.appliance_type} "
                f"service in {args.zip_code}."
            ),
            "slots": [],
        }
    return {
        "status": "ok",
        "slots": [s.model_dump(mode="json") for s in slots],
    }


# ---------- book_appointment ----------

async def handle_book_appointment(
    args: BookAppointmentInput, ctx: ToolContext
) -> Dict[str, Any]:
    customer_phone = (
        normalize_phone(args.customer_phone)
        or args.customer_phone
        or ctx.call.from_number
    )
    if not customer_phone:
        return {
            "status": "error",
            "message": "Need a callback phone number before booking.",
        }

    service = SchedulingService(ctx.session)
    try:
        appt = await service.book_appointment(
            AppointmentCreateDTO(
                customer_name=args.customer_name,
                customer_phone=customer_phone,
                customer_email=args.customer_email or ctx.call.customer_email,
                customer_address=args.service_address or ctx.call.customer_address,
                service_zip=args.service_zip,
                appliance_type=args.appliance_type,
                issue_summary=args.issue_summary,
                availability_id=args.availability_id,
            )
        )
    except SchedulingError as exc:
        return {"status": "error", "message": str(exc)}

    ctx.call.outcome = "appointment_booked"
    # Stash the booked appointment id so the bridge can link CallRecord -> Appointment.
    ctx.call.booked_appointment_id = appt.id
    return {"status": "ok", "appointment": appt.model_dump(mode="json")}


# ---------- request_image_upload ----------

async def handle_request_image_upload(
    args: RequestImageUploadInput, ctx: ToolContext
) -> Dict[str, Any]:
    if not ctx.call.from_number:
        return {
            "status": "error",
            "message": "Need a phone number to associate the upload link with a customer.",
        }
    upload_service = UploadService(ctx.session)
    link = await upload_service.issue_link(
        customer_email=args.customer_email,
        customer_phone=ctx.call.from_number,
        appliance_type=args.appliance_type or ctx.call.appliance_type,
        call_sid=ctx.call.call_sid,
    )

    email_service = EmailService()
    try:
        await email_service.send_upload_link(
            to_address=args.customer_email,
            upload_url=link.upload_url or "",
            appliance_type=args.appliance_type or ctx.call.appliance_type,
        )
    except Exception as exc:  # email delivery is best-effort during a live call
        logger.warning("Upload email failed | err={}", exc)
        return {
            "status": "partial",
            "message": (
                "I created the upload link but couldn't send the email. "
                "I'll have the team retry it shortly."
            ),
            "upload_url": link.upload_url,
        }

    ctx.call.outcome = ctx.call.outcome or "image_requested"
    return {
        "status": "ok",
        "message": f"Upload link emailed to {args.customer_email}.",
        "upload_url": link.upload_url,
        "expires_at": link.expires_at.isoformat(),
    }
