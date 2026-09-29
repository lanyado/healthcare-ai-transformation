"""Explicit Redis storage and the small downstream-preparation wrapper."""

from __future__ import annotations

import json
import logging
from typing import Any

from .config import DEFAULT_TTL_SECONDS, REDIS_URL
from .entity_resolution import FakeCRMHandler, resolve_and_anonymize

logger = logging.getLogger(__name__)


def entity_map_key(interaction_id: str) -> str:
    if not interaction_id.strip():
        logger.error("interaction_id must not be empty")
        raise ValueError("interaction_id must not be empty")
    return f"extraction:entity-map:{interaction_id.strip()}"


def _redis_client(redis_url: str):
    try:
        import redis
    except ImportError as exc:
        logger.exception("Redis package is not installed")
        raise RuntimeError("Install the 'redis' package to use Redis storage") from exc
    return redis.Redis.from_url(redis_url, decode_responses=True)


def _client(redis_client, redis_url: str):
    return redis_client or _redis_client(redis_url)


def save_entity_map(
    interaction_id: str,
    entity_map: dict[str, dict[str, Any]],
    *,
    redis_client=None,
    redis_url: str = REDIS_URL,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> None:
    if ttl_seconds <= 0:
        logger.error("ttl_seconds must be positive")
        raise ValueError("ttl_seconds must be positive")
    try:
        _client(redis_client, redis_url).set(
            entity_map_key(interaction_id),
            json.dumps(entity_map, sort_keys=True),
            ex=ttl_seconds,
        )
    except Exception:
        logger.exception("Failed to save entity map for %s", interaction_id)
        raise
    logger.info("Saved entity map for %s (%s entries)", interaction_id, len(entity_map))


def load_entity_map(
    interaction_id: str,
    *,
    redis_client=None,
    redis_url: str = REDIS_URL,
) -> dict[str, dict[str, Any]] | None:
    try:
        value = _client(redis_client, redis_url).get(entity_map_key(interaction_id))
    except Exception:
        logger.exception("Failed to load entity map for %s", interaction_id)
        raise
    if value is None:
        logger.warning("No entity map for %s", interaction_id)
        return None
    if isinstance(value, bytes):
        value = value.decode()
    return json.loads(value)


def delete_entity_map(
    interaction_id: str,
    *,
    redis_client=None,
    redis_url: str = REDIS_URL,
) -> None:
    """Delete the private map after its results are safely stored."""

    try:
        _client(redis_client, redis_url).delete(entity_map_key(interaction_id))
    except Exception:
        logger.exception("Failed to delete entity map for %s", interaction_id)
        raise
    logger.info("Deleted entity map for %s", interaction_id)


def prepare_transcript_for_extraction(
    interaction_id: str,
    patient_id: str,
    transcript: str,
    *,
    crm_handler=None,
    redis_client=None,
    redis_url: str = REDIS_URL,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    """Resolve entities, save the private map, and return the anonymized transcript."""

    try:
        result = resolve_and_anonymize(transcript, patient_id, crm_handler or FakeCRMHandler())
        save_entity_map(
            interaction_id,
            result.entity_map,
            redis_client=redis_client,
            redis_url=redis_url,
            ttl_seconds=ttl_seconds,
        )
    except Exception:
        logger.exception(
            "Failed to prepare transcript for %s / %s",
            interaction_id,
            patient_id,
        )
        raise
    logger.info("Prepared transcript for %s / %s", interaction_id, patient_id)
    return result.anonymized_transcript
