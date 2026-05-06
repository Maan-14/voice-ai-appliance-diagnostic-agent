"""Centralized logging configuration."""
from __future__ import annotations

import logging
import sys
from typing import Any

from loguru import logger

from app.config.settings import get_settings


class _InterceptHandler(logging.Handler):
    """Forward stdlib `logging` records to loguru."""

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def configure_logging() -> None:
    """Configure loguru once and route stdlib loggers through it."""
    settings = get_settings()

    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.app.log_level.upper(),
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        backtrace=settings.app.env != "production",
        diagnose=settings.app.env != "production",
        enqueue=True,
    )

    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi", "sqlalchemy.engine"):
        std_logger = logging.getLogger(name)
        std_logger.handlers = [_InterceptHandler()]
        std_logger.propagate = False


def get_logger(name: str | None = None) -> Any:
    """Return a loguru logger bound to a name."""
    return logger.bind(component=name) if name else logger
