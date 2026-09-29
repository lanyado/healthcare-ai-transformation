"""Jev check that a custom upload is a healthcare call transcript."""

from __future__ import annotations

import json
import logging
from typing import Any

from .config import JEV_MODEL, OPENROUTER_URL, RELEVANCE_PROMPT_PATH, RELEVANCE_THRESHOLD, require_api_key
from .prompt_guard import prompt_injection_warning

logger = logging.getLogger(__name__)
RELEVANCE_QUESTIONS = json.loads(RELEVANCE_PROMPT_PATH.read_text())
IRRELEVANT = "This does not look like a healthcare call transcript. Use a member-services call."


def is_healthcare_transcript(
    transcript: str,
    *,
    client: Any | None = None,
    threshold: float = RELEVANCE_THRESHOLD,
) -> bool:
    """Return True when Jev scores the text as a healthcare member-services call."""

    try:
        if client is None:
            from typesafe_sdk import TypeSafeClient

            with TypeSafeClient(
                api_key=require_api_key(),
                base_url=OPENROUTER_URL,
                model=JEV_MODEL,
            ) as openrouter_client:
                score = float(openrouter_client.system_one(transcript, RELEVANCE_QUESTIONS).nouls["healthcare_call"].noul)
        else:
            score = float(client.system_one(transcript, RELEVANCE_QUESTIONS).nouls["healthcare_call"].noul)
    except Exception:
        logger.exception("Healthcare relevance check failed")
        raise
    logger.info("Healthcare relevance score %.2f", score)
    return score >= threshold


def custom_transcript_warning(transcript: str, *, client: Any | None = None) -> str | None:
    """Injection first, then Jev relevance. None means the custom text is usable."""

    injection = prompt_injection_warning(transcript)
    if injection:
        return injection
    try:
        if is_healthcare_transcript(transcript, client=client):
            return None
    except Exception:
        return "Could not confirm this is a healthcare call transcript. Try again."
    return IRRELEVANT
