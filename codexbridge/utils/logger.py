from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from codexbridge.config import AppSettings


def configure_logging(settings: AppSettings) -> None:
    log_file = Path(settings.logs_dir) / "server.log"
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} | {message}",
    )
    logger.add(
        log_file,
        level=settings.log_level,
        rotation="10 MB",
        retention=10,
        enqueue=True,
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {message}",
    )
