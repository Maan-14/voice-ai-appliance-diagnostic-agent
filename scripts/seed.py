"""Idempotent seed script.

Populates 7 technicians across multiple ZIPs and appliance specialties,
plus a generous spread of availability slots over the next 14 days so the
agent always has something to offer callers.

Run via:  python -m scripts.seed
"""
from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta, timezone
from typing import Iterable, List, Tuple

from sqlalchemy import select

from app.config.logging_config import configure_logging, get_logger
from app.database.session import db_manager, init_db
from app.models.availability import Availability
from app.models.service_area import ServiceArea
from app.models.specialty import Specialty
from app.models.technician import Technician

configure_logging()
logger = get_logger("seed")


# (name, email, phone, employee_code, employment_type, zips, appliances)
TECHNICIANS: List[Tuple[str, str, str, str, str, List[str], List[str]]] = [
    (
        "Marcus Chen", "marcus.chen@example.com", "+13125550101",
        "T-1001", "full_time",
        ["60601", "60602", "60603", "60610"],
        ["washer", "dryer", "dishwasher"],
    ),
    (
        "Priya Desai", "priya.desai@example.com", "+13125550102",
        "T-1002", "full_time",
        ["60601", "60607", "60611", "60614"],
        ["refrigerator", "oven", "microwave"],
    ),
    (
        "Tomás Reyes", "tomas.reyes@example.com", "+13125550103",
        "T-1003", "contractor",
        ["60615", "60616", "60617"],
        ["hvac", "refrigerator"],
    ),
    (
        "Aisha Williams", "aisha.williams@example.com", "+13125550104",
        "T-1004", "full_time",
        ["60618", "60619", "60620", "60622"],
        ["washer", "dryer", "oven", "microwave"],
    ),
    (
        "Daniel O'Connor", "daniel.oconnor@example.com", "+13125550105",
        "T-1005", "full_time",
        ["60625", "60626", "60630"],
        ["dishwasher", "refrigerator", "oven"],
    ),
    (
        "Sofia Petrova", "sofia.petrova@example.com", "+13125550106",
        "T-1006", "part_time",
        ["60601", "60618", "60625"],
        ["hvac", "washer"],
    ),
    (
        "Jamal Hayes", "jamal.hayes@example.com", "+13125550107",
        "T-1007", "full_time",
        ["60607", "60616", "60622", "60630"],
        ["microwave", "dishwasher", "oven", "refrigerator"],
    ),
]


def _slot_starts(days: int = 14) -> Iterable[datetime]:
    """Generate 9 AM, 11 AM, 1 PM, 3 PM slots for the next `days` weekdays."""
    now = datetime.now(timezone.utc).replace(microsecond=0, second=0, minute=0)
    base_day = now.date() + timedelta(days=1)
    for day_offset in range(days):
        d = base_day + timedelta(days=day_offset)
        if d.weekday() >= 5:  # skip weekends
            continue
        for hour in (9, 11, 13, 15):
            yield datetime.combine(d, time(hour, 0), tzinfo=timezone.utc)


async def _ensure_technician(session, spec) -> Technician:
    name, email, phone, code, etype, zips, appliances = spec
    existing = (
        await session.execute(
            select(Technician).where(Technician.employee_code == code)
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    tech = Technician(
        name=name,
        email=email,
        phone=phone,
        employee_code=code,
        employment_type=etype,
        is_active=True,
    )
    tech.service_areas = [ServiceArea(zip_code=z) for z in zips]
    tech.specialties = [Specialty(appliance_type=a) for a in appliances]
    session.add(tech)
    await session.flush()
    logger.info("Inserted technician {} ({})", name, code)
    return tech


async def _ensure_availability(session, tech_id: int) -> int:
    inserted = 0
    for start in _slot_starts():
        existing = (
            await session.execute(
                select(Availability).where(
                    Availability.technician_id == tech_id,
                    Availability.start_at == start,
                )
            )
        ).scalar_one_or_none()
        if existing:
            continue
        session.add(
            Availability(
                technician_id=tech_id,
                start_at=start,
                end_at=start + timedelta(hours=2),
                is_booked=False,
            )
        )
        inserted += 1
    await session.flush()
    return inserted


async def main() -> None:
    await init_db()
    async with db_manager.session() as session:
        for spec in TECHNICIANS:
            tech = await _ensure_technician(session, spec)
            count = await _ensure_availability(session, tech.id)
            if count:
                logger.info("Inserted {} slots for {}", count, tech.name)
    logger.info("Seed complete")


if __name__ == "__main__":
    asyncio.run(main())
