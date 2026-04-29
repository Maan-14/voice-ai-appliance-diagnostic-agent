"""Drop and recreate every project-managed table.

Use this when you've changed the schema in app/models/* and want a clean
database to match. Equivalent to: ``DROP SCHEMA public CASCADE`` for the
tables we own, then ``init_db`` to recreate.

Run via:  python -m scripts.reset_db
"""
from __future__ import annotations

import asyncio

from app.config.logging_config import configure_logging, get_logger
from app.database.session import db_manager, dispose_db, init_db
from app.models.base import Base
# Import all models so Base.metadata knows about them.
from app.models import (  # noqa: F401
    customer,
    technician,
    service_area,
    specialty,
    availability,
    appointment,
    upload_link,
    call_record,
)

configure_logging()
logger = get_logger("reset_db")


async def main() -> None:
    async with db_manager.engine.begin() as conn:
        logger.warning("Dropping all project-managed tables…")
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()
    await dispose_db()
    logger.info("Reset complete — schema is fresh, no rows.")


if __name__ == "__main__":
    asyncio.run(main())
