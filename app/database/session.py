"""Async SQLAlchemy engine + session factory.

Uses a small DatabaseManager singleton so the engine is created once and
shared, and `get_session()` is a FastAPI dependency that yields an
`AsyncSession` per request with proper transaction lifecycle.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator, AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config.settings import get_settings
from app.config.logging_config import get_logger

logger = get_logger(__name__)


class DatabaseManager:
    """Singleton-style holder for the async engine + session factory."""

    _instance: "DatabaseManager | None" = None

    def __new__(cls) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        settings = get_settings()
        self._engine: AsyncEngine = create_async_engine(
            settings.database.url,
            echo=settings.database.echo,
            pool_pre_ping=True,
            future=True,
        )
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        self._initialized = True
        logger.info("DatabaseManager initialised | url={}", settings.database.url)

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self._session_factory

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def dispose(self) -> None:
        await self._engine.dispose()
        logger.info("Database engine disposed")


db_manager = DatabaseManager()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an AsyncSession per request."""
    async with db_manager.session() as session:
        yield session


async def init_db() -> None:
    """Create tables. For real deployments use Alembic; this is for first-boot bootstrap."""
    from app.models.base import Base
    # Import models so they register on Base.metadata
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

    async with db_manager.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured")


async def dispose_db() -> None:
    await db_manager.dispose()
