"""Demo helper — simulate a customer booking from the command line.

Drives the same SchedulingService / UploadService that the live agent
calls during a phone conversation. Useful for end-to-end demos where
you want to show data flowing into pgAdmin without setting up Twilio.

Run via:  python -m scripts.demo_booking
"""
from __future__ import annotations

import asyncio

from app.config.logging_config import configure_logging, get_logger
from app.database.session import db_manager, dispose_db
from app.dto.appointment import AppointmentCreateDTO
from app.services.scheduling_service import SchedulingService
from app.services.upload_service import UploadService

configure_logging()
logger = get_logger("demo")


async def main() -> None:
    print("\n=== 1. Customer 'Jane Doe' calls about a leaking washer in 60601 ===")
    async with db_manager.session() as s:
        slots = await SchedulingService(s).find_available_slots(
            zip_code="60601", appliance_type="washer", max_slots=3
        )
    print(f"Agent would offer {len(slots)} slot(s):")
    for sl in slots:
        print(f"  - id={sl.availability_id}  {sl.technician_name}  {sl.start_at:%a %b %d, %I:%M %p}")

    print("\n=== 2. Jane picks the first slot — book_appointment runs ===")
    async with db_manager.session() as s:
        appt = await SchedulingService(s).book_appointment(
            AppointmentCreateDTO(
                customer_name="Jane Doe",
                customer_phone="+13125551234",
                customer_email="jane@example.com",
                customer_address="221B Wabash Ave, Chicago",
                service_zip="60601",
                appliance_type="washer",
                issue_summary="Leaking from underneath, error code LE",
                availability_id=slots[0].availability_id,
            )
        )
    print(f"  Booked appointment id={appt.id}")
    print(f"  Confirmation:        {appt.confirmation_code}")
    print(f"  Customer id:         {appt.customer_id}  ({appt.customer_name})")
    print(f"  Technician:          {appt.technician_name}")
    print(f"  When:                {appt.scheduled_start:%a %b %d, %I:%M %p}")

    print("\n=== 3. Jane asks for an upload link too ===")
    async with db_manager.session() as s:
        link = await UploadService(s).issue_link(
            customer_email="jane@example.com",
            customer_phone="+13125551234",
            appliance_type="washer",
            call_sid="CA-demo-001",
        )
    print(f"  Upload token:  {link.token}")
    print(f"  Customer id:   {link.customer_id}  (same as the booking — upserted)")
    print(f"  Expires:       {link.expires_at:%Y-%m-%d %H:%M %Z}")
    print(f"  URL:           {link.upload_url}")

    print("\n=== 4. A second customer 'Tomás' books a fridge service in 60615 ===")
    async with db_manager.session() as s:
        slots = await SchedulingService(s).find_available_slots(
            zip_code="60615", appliance_type="refrigerator", max_slots=2
        )
        appt2 = await SchedulingService(s).book_appointment(
            AppointmentCreateDTO(
                customer_name="Tomás Reyes",
                customer_phone="+17735557777",
                customer_email="tomas@example.com",
                service_zip="60615",
                appliance_type="refrigerator",
                issue_summary="Fridge not cooling, food spoiling",
                availability_id=slots[0].availability_id,
            )
        )
    print(f"  Booked id={appt2.id}  customer_id={appt2.customer_id}  code={appt2.confirmation_code}")

    print("\n✓ Demo complete — check pgAdmin (or sqlite3) to inspect:")
    print("  customers       (now 2 rows)")
    print("  appointments    (now 2 rows, both CONFIRMED)")
    print("  upload_links    (now 1 row, status PENDING)")
    print("  availabilities  (2 rows now have is_booked=true)")

    await dispose_db()


if __name__ == "__main__":
    asyncio.run(main())
