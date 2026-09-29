"""Redis Streams used as a simple job queue.

Extraction jobs carry a call ID. CRM jobs carry only a pointer to result.json.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .config import MAX_JOB_ATTEMPTS, REDIS_URL, SCHEMA_VERSION

logger = logging.getLogger(__name__)

JOBS = "extraction:jobs"
CRM_JOBS = "crm:jobs"


def connect(redis=None):
    if redis is not None:
        return redis
    import redis as redis_lib

    return redis_lib.Redis.from_url(REDIS_URL, decode_responses=True)


def _attempts(fields: dict[str, Any]) -> int:
    try:
        return max(1, int(fields.get("attempts", 1)))
    except (TypeError, ValueError):
        return 1


def enqueue(call_id: str, redis=None, attempts: int = 1) -> str:
    call_id = call_id.strip()
    client = connect(redis)
    set_status(call_id, "queued", redis=client)
    message_id = client.xadd(JOBS, {"call_id": call_id, "attempts": str(attempts)})
    logger.info("Queued extraction %s (attempt %s)", call_id, attempts)
    return str(message_id)


def read_job(redis=None, wait_ms: int = 1000) -> tuple[str, str, int] | None:
    """Return (message_id, call_id, attempts) for the oldest extraction job, or None."""

    response = connect(redis).xread({JOBS: "0"}, count=1, block=wait_ms)
    if not response:
        return None
    _stream, messages = response[0]
    message_id, fields = messages[0]
    return str(message_id), fields["call_id"], _attempts(fields)


def finish_job(message_id: str, redis=None) -> None:
    connect(redis).xdel(JOBS, message_id)


def retry_job(call_id: str, attempts: int, redis=None) -> bool:
    if attempts >= MAX_JOB_ATTEMPTS:
        return False
    enqueue(call_id, redis=redis, attempts=attempts + 1)
    return True


def enqueue_crm(interaction_id: str, result_uri: str, redis=None, attempts: int = 1) -> str:
    pointer = {
        "interaction_id": interaction_id,
        "result_uri": result_uri,
        "schema_version": SCHEMA_VERSION,
        "attempts": str(attempts),
    }
    message_id = connect(redis).xadd(CRM_JOBS, pointer)
    logger.info("Queued CRM write for %s (attempt %s)", interaction_id, attempts)
    return str(message_id)


def read_crm_job(redis=None, wait_ms: int = 1000) -> tuple[str, dict[str, Any]] | None:
    """Return (message_id, pointer) for the oldest CRM job, or None."""

    response = connect(redis).xread({CRM_JOBS: "0"}, count=1, block=wait_ms)
    if not response:
        return None
    _stream, messages = response[0]
    message_id, fields = messages[0]
    return str(message_id), {
        "interaction_id": fields["interaction_id"],
        "result_uri": fields["result_uri"],
        "schema_version": fields.get("schema_version", SCHEMA_VERSION),
        "attempts": _attempts(fields),
    }


def retry_crm_job(pointer: dict[str, Any], redis=None) -> bool:
    attempts = int(pointer.get("attempts") or 1)
    if attempts >= MAX_JOB_ATTEMPTS:
        return False
    enqueue_crm(pointer["interaction_id"], pointer["result_uri"], redis=redis, attempts=attempts + 1)
    return True


def finish_crm_job(message_id: str, redis=None) -> None:
    connect(redis).xdel(CRM_JOBS, message_id)


def set_status(call_id: str, status: str, extra: dict[str, Any] | None = None, redis=None) -> None:
    body = {"call_id": call_id, "status": status, **(extra or {})}
    connect(redis).set(f"extraction:status:{call_id}", json.dumps(body))


def get_status(call_id: str, redis=None) -> dict[str, Any] | None:
    value = connect(redis).get(f"extraction:status:{call_id}")
    return json.loads(value) if value else None
