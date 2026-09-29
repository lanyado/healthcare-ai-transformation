"""Classify transcript topics with TypeSafe Jev through OpenRouter."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Any

from .config import JEV_MODEL, OPENROUTER_URL, TOPIC_PROMPT_PATH, TOPIC_THRESHOLD, require_api_key

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TopicClassificationResult:
    topics: list[str]
    scores: dict[str, float]


def load_topic_questions(path: Path = TOPIC_PROMPT_PATH) -> dict[str, dict[str, Any]]:
    try:
        return json.loads(path.read_text())
    except Exception:
        logger.exception("Failed to load topic questions from %s", path)
        raise


def _classify(client: Any, transcript: str, threshold: float) -> TopicClassificationResult:
    questions = load_topic_questions()
    response = client.system_one(transcript, questions)
    scores = {topic: float(response.nouls[topic].noul) for topic in questions}
    return TopicClassificationResult(
        topics=[topic for topic, score in scores.items() if score >= threshold],
        scores=scores,
    )


def classify_topics(
    transcript: str,
    *,
    threshold: float = TOPIC_THRESHOLD,
    client: Any | None = None,
    api_key: str | None = None,
) -> TopicClassificationResult:
    """Return Jev topic probabilities and the topics meeting the threshold."""

    try:
        if client is not None:
            result = _classify(client, transcript, threshold)
        else:
            from typesafe_sdk import TypeSafeClient

            with TypeSafeClient(
                api_key=require_api_key(api_key),
                base_url=OPENROUTER_URL,
                model=JEV_MODEL,
            ) as openrouter_client:
                result = _classify(openrouter_client, transcript, threshold)
    except Exception:
        logger.exception("Topic classification failed")
        raise
    logger.info("Classified %s topics: %s", len(result.topics), ", ".join(result.topics) or "none")
    return result
