"""Immutable extraction artifacts in S3 (MinIO locally).

S3 keeps the full validated AI record. The CRM queue only carries a pointer.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from .config import (
    EXTRACTOR_PROMPT_PATH,
    GPT_MODEL,
    JEV_MODEL,
    REPO_ROOT,
    S3_ACCESS_KEY,
    S3_BUCKET,
    S3_ENDPOINT,
    S3_REGION,
    S3_SECRET_KEY,
    SCHEMA_VERSION,
    SCORER_PROMPT_PATH,
    SUMMARIZER_PROMPT_PATH,
    TOPIC_PROMPT_PATH,
)

logger = logging.getLogger(__name__)

REQUIRED_ARTIFACT = ("interaction_id", "patient_id", "schema_version", "topics", "metadata")
REQUIRED_TOPIC = ("topic", "sentiment", "resolved", "urgency")
REQUIRED_METADATA = ("models", "processed_at", "job_id")


RECORDINGS = {
    "call_001": REPO_ROOT / "artifacts/audio/call-0-denial-two-voices.mp3",
    "call_002": REPO_ROOT / "artifacts/audio/call-1-prior-auth-two-voices.mp3",
    "call_003": REPO_ROOT / "artifacts/audio/call-2-contact-benefits-two-voices.mp3",
    "call_004": REPO_ROOT / "artifacts/audio/benefits-call-two-voices.mp3",
    "call_005": REPO_ROOT / "artifacts/audio/call-4-appeal-two-voices.mp3",
}


def result_key(interaction_id: str) -> str:
    return f"calls/{interaction_id}/extraction/v1/result.json"


def recording_key(call_id: str) -> str:
    return f"calls/{call_id}/recording.mp3"


def transcript_key(call_id: str) -> str:
    return f"calls/{call_id}/transcript.json"


def result_uri(interaction_id: str) -> str:
    return f"s3://{S3_BUCKET}/{result_key(interaction_id)}"


def parse_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"Not an S3 URI: {uri}")
    bucket, key = uri[5:].split("/", 1)
    return bucket, key


def connect(s3=None):
    if s3 is not None:
        return s3
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name=S3_REGION,
        config=Config(s3={"addressing_style": "path"}),
    )


def ensure_bucket(s3=None) -> None:
    client = connect(s3)
    try:
        client.head_bucket(Bucket=S3_BUCKET)
    except Exception:
        client.create_bucket(Bucket=S3_BUCKET)
        logger.info("Created S3 bucket %s", S3_BUCKET)


def put_json(key: str, body: dict[str, Any], s3=None) -> str:
    client = connect(s3)
    ensure_bucket(s3=client)
    client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(body, indent=2),
        ContentType="application/json",
    )
    return f"s3://{S3_BUCKET}/{key}"


def put_transcript(call_id: str, lines: list[str], s3=None) -> str:
    """Store the raw transcript lines. Postgres keeps call metadata only."""

    client = connect(s3)
    ensure_bucket(s3=client)
    key = transcript_key(call_id)
    client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(lines),
        ContentType="application/json",
    )
    uri = f"s3://{S3_BUCKET}/{key}"
    logger.info("Saved transcript %s", uri)
    return uri


def get_transcript(call_id: str, s3=None) -> list[str]:
    try:
        body = connect(s3).get_object(Bucket=S3_BUCKET, Key=transcript_key(call_id))["Body"].read()
    except Exception:
        logger.warning("No transcript in S3 for %s", call_id)
        return []
    if isinstance(body, bytes):
        body = body.decode()
    lines = json.loads(body)
    return [str(line) for line in lines] if isinstance(lines, list) else []


def get_json(uri: str, s3=None) -> dict[str, Any]:
    bucket, key = parse_uri(uri)
    body = connect(s3).get_object(Bucket=bucket, Key=key)["Body"].read()
    if isinstance(body, bytes):
        body = body.decode()
    return json.loads(body)


def validate_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    missing = [key for key in REQUIRED_ARTIFACT if key not in artifact]
    if missing:
        raise ValueError(f"Invalid result.json: missing {missing}")
    if artifact["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema_version: {artifact['schema_version']}")
    if not isinstance(artifact["topics"], list):
        raise ValueError("topics must be a list")
    metadata = artifact["metadata"]
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")
    missing_meta = [key for key in REQUIRED_METADATA if key not in metadata]
    if missing_meta:
        raise ValueError(f"Invalid result.json metadata: missing {missing_meta}")
    for topic in artifact["topics"]:
        if not isinstance(topic, dict):
            raise ValueError("each topic must be an object")
        missing_topic = [key for key in REQUIRED_TOPIC if key not in topic]
        if missing_topic:
            raise ValueError(f"Invalid topic {topic.get('topic')}: missing {missing_topic}")
        for score_name in ("sentiment", "resolved", "urgency"):
            float(topic[score_name])
    return artifact


def build_artifact(
    interaction_id: str,
    patient_id: str,
    results: dict[str, dict[str, Any]],
    *,
    job_id: str | None = None,
) -> dict[str, Any]:
    topics = []
    compliance = []
    for topic_id, result in results.items():
        scores = result.get("scores") or {}
        extraction = result.get("extraction") or {}
        claim_id = extraction.get("claim_id")
        claim_ids = claim_id if isinstance(claim_id, list) else ([claim_id] if claim_id else [])
        topic = {
            "topic": topic_id,
            "sentiment": scores["sentiment"],
            "resolved": scores["resolved"],
            "urgency": scores["urgency"],
            "compliance_concern": scores.get("compliance_concern"),
            "agent_actions": list(extraction.get("agent_actions_taken") or []),
            "agent_commitments": list(extraction.get("agent_commitments") or []),
            "caller_commitments": list(extraction.get("caller_commitments") or []),
            "claim_ids": [str(item) for item in claim_ids if str(item).strip()],
            "summary": extraction.get("summary") or "",
        }
        topics.append(topic)
        if scores.get("compliance_concern") is not None:
            compliance.append(float(scores["compliance_concern"]))

    artifact = {
        "interaction_id": interaction_id,
        "patient_id": patient_id,
        "schema_version": SCHEMA_VERSION,
        "topics": topics,
        "compliance_flags": max(compliance) if compliance else 0,
        "metadata": {
            "models": {
                "classifier": JEV_MODEL,
                "scorer": JEV_MODEL,
                "extractor": GPT_MODEL,
                "summarizer": GPT_MODEL,
            },
            "prompts": {
                "classifier": TOPIC_PROMPT_PATH.name,
                "scorer": SCORER_PROMPT_PATH.name,
                "extractor": EXTRACTOR_PROMPT_PATH.name,
                "summarizer": SUMMARIZER_PROMPT_PATH.name,
            },
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "job_id": job_id or str(uuid.uuid4()),
        },
    }
    return validate_artifact(artifact)


def crm_rows(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Operational fields only. Model/prompt metadata stays on S3."""

    rows = {}
    for topic in artifact["topics"]:
        claim_ids = topic.get("claim_ids") or []
        rows[topic["topic"]] = {
            "scores": {
                "resolved": topic["resolved"],
                "urgency": topic["urgency"],
                "sentiment": topic["sentiment"],
                "compliance_concern": topic.get("compliance_concern", artifact.get("compliance_flags", 0)),
            },
            "extraction": {
                "claim_id": [str(item) for item in claim_ids if str(item).strip()],
                "agent_actions_taken": list(topic.get("agent_actions") or []),
                "agent_commitments": list(topic.get("agent_commitments") or []),
                "caller_commitments": list(topic.get("caller_commitments") or []),
                "summary": topic.get("summary") or "",
            },
        }
    return rows


def put_result(artifact: dict[str, Any], s3=None) -> str:
    validate_artifact(artifact)
    uri = put_json(result_key(artifact["interaction_id"]), artifact, s3=s3)
    logger.info("Saved extraction artifact %s", uri)
    return uri


def get_result(uri: str, s3=None) -> dict[str, Any]:
    return validate_artifact(get_json(uri, s3=s3))


def seed_recordings(s3=None) -> None:
    """Copy the local HarborPoint call audio files into S3 if they are missing."""

    client = connect(s3)
    ensure_bucket(s3=client)
    for call_id, path in RECORDINGS.items():
        if not path.is_file():
            logger.warning("Missing recording file %s", path)
            continue
        key = recording_key(call_id)
        try:
            client.head_object(Bucket=S3_BUCKET, Key=key)
            continue
        except Exception:
            pass
        client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=path.read_bytes(),
            ContentType="audio/mpeg",
        )
        logger.info("Uploaded recording %s", key)


def parse_byte_range(header: str | None, size: int) -> tuple[int, int] | None:
    if not header or not header.lower().startswith("bytes=") or size <= 0:
        return None
    spec = header.split("=", 1)[1].split(",", 1)[0]
    left, _, right = spec.partition("-")
    try:
        if left == "" and right:
            start = max(size - int(right), 0)
            return start, size - 1
        start = int(left)
        end = int(right) if right else size - 1
    except ValueError:
        return None
    end = min(end, size - 1)
    if start < 0 or start > end:
        return None
    return start, end


def recording_info(call_id: str, s3=None) -> tuple[int, str]:
    key = recording_key(call_id)
    try:
        head = connect(s3).head_object(Bucket=S3_BUCKET, Key=key)
    except Exception as exc:
        raise FileNotFoundError(key) from exc
    return int(head["ContentLength"]), head.get("ContentType") or "audio/mpeg"


def get_recording(call_id: str, s3=None, start: int | None = None, end: int | None = None):
    size, content_type = recording_info(call_id, s3=s3)
    extra = {}
    if start is not None:
        extra["Range"] = f"bytes={start}-{end if end is not None else size - 1}"
    try:
        obj = connect(s3).get_object(Bucket=S3_BUCKET, Key=recording_key(call_id), **extra)
    except Exception as exc:
        raise FileNotFoundError(recording_key(call_id)) from exc
    return obj["Body"], obj.get("ContentType") or content_type, size
