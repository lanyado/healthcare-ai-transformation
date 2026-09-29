"""Write backend logs to a local rotating file."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import LOG_LEVEL, LOG_PATH

_configured = False


def configure_logging(log_path: Path | None = None, *, force: bool = False) -> Path:
    """Attach a file handler to the `app` logger. Safe to call more than once."""

    global _configured
    path = Path(log_path or LOG_PATH)
    logger = logging.getLogger("app")
    if _configured and not force:
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=1_048_576, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    if force:
        kept = []
        for existing in logger.handlers:
            if isinstance(existing, RotatingFileHandler):
                existing.close()
                continue
            kept.append(existing)
        logger.handlers = kept

    logger.setLevel(getattr(logging, str(LOG_LEVEL).upper(), logging.INFO))
    logger.addHandler(handler)
    _configured = True
    logger.debug("Writing logs to %s", path)
    return path
