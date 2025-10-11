"""Structlog JSON logging configuration.

This module centralizes logging setup to ensure consistent structured logs
across API, bot, workers, and scripts.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def setup_logging(level: str = "INFO") -> None:
    """Configure structlog and standard logging.

    Args:
        level: Log level string (e.g., "INFO").
    """

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list[Any] = [
        structlog.processors.add_log_level,
        timestamper,
    ]

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.dict_tracebacks,
            *shared_processors,
            structlog.processors.EventRenamer(to="message"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
        force=True,
    )

    # Make uvicorn/fastapi handlers play nice with structlog formatting.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logging.getLogger(logger_name).handlers = []

