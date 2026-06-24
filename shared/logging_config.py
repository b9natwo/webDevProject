"""
shared/logging_config.py
Structured logging configuration for all services.
"""
from __future__ import annotations

import logging
import sys
from typing import Any


def configure_logging(level: str = "INFO", service_name: str = "prefix-hub") -> None:
    """
    Configure root logger with a consistent structured format.
    Call once at service startup before any other imports log.
    """
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Quieten noisy third-party loggers
    for noisy in ("discord.gateway", "discord.client", "discord.http", "aiohttp", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger(service_name).setLevel(getattr(logging, level.upper(), logging.INFO))


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Use module __name__ as the name."""
    return logging.getLogger(name)
