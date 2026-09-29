"""One extraction job: run the pipeline, save result.json, then enqueue a CRM pointer."""

from __future__ import annotations

import logging
from typing import Any

from .artifacts import build_artifact, put_result
from .call_reconnect import merge_reconnect
from .crm_handler import crm
from .privacy import delete_entity_map, load_entity_map, prepare_transcript_for_extraction
from .queue import enqueue_crm, set_status
from .result_finalization import reassociate_entities
from .topic_classification import classify_topics
from .topic_processing import process_topics

logger = logging.getLogger(__name__)


def _transcript_text(call: dict[str, Any]) -> str:
    transcript = call["transcript"]
    return "\n".join(transcript) if isinstance(transcript, list) else str(transcript)


async def run_extraction_job(call_id: str, redis=None, s3=None) -> dict[str, Any]:
    requested_id = call_id
    set_status(requested_id, "processing", redis=redis)
    call = crm.load_call(requested_id)
    if call is None:
        set_status(requested_id, "error", {"error": f"Unknown call_id: {requested_id}"}, redis=redis)
        raise LookupError(f"Unknown call_id: {requested_id}")

    try:
        merged = merge_reconnect(call)
        if merged:
            call = merged
            set_status(requested_id, "processing", {"merged_into": call["call_id"]}, redis=redis)

        call_id = call["call_id"]
        patient_id = call["member_id"]
        transcript = _transcript_text(call)

        anonymized = prepare_transcript_for_extraction(
            call_id,
            patient_id,
            transcript,
            crm_handler=crm,
            redis_client=redis,
        )
        classified = classify_topics(anonymized)
        results = {}
        if classified.topics:
            results = await process_topics(anonymized, list(classified.topics))
        entity_map = load_entity_map(call_id, redis_client=redis)
        if entity_map is None:
            raise ValueError(f"No entity map found for {call_id}")
        reassociated = reassociate_entities(results, entity_map)
        artifact = build_artifact(call_id, patient_id, reassociated)
        uri = put_result(artifact, s3=s3)
        delete_entity_map(call_id, redis_client=redis)
        enqueue_crm(call_id, uri, redis=redis)
        extra = {"result_uri": uri}
        if call_id != requested_id:
            extra["merged_into"] = call_id
            set_status(requested_id, "extracted", extra, redis=redis)
        set_status(call_id, "extracted", extra, redis=redis)
        return artifact
    except Exception:
        logger.exception("Extraction failed for %s", requested_id)
        set_status(requested_id, "error", {"error": "Extraction failed."}, redis=redis)
        raise
