"""Run scoring and extraction for each selected topic."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from .config import (
    EXTRACTOR_PROMPT_PATH,
    GPT_MODEL,
    JEV_MODEL,
    OPENAI_OPENROUTER_URL,
    OPENROUTER_URL,
    REQUESTED_FIELDS,
    SCORER_PROMPT_PATH,
    SUMMARIZER_PROMPT_PATH,
    require_api_key,
)


logger = logging.getLogger(__name__)
SCORER_QUESTIONS = json.loads(SCORER_PROMPT_PATH.read_text())
EXTRACTOR_TEMPLATE = EXTRACTOR_PROMPT_PATH.read_text()
SUMMARIZER_TEMPLATE = SUMMARIZER_PROMPT_PATH.read_text()
MAX_LIST_ITEM_CHARS = 150
LIST_FIELDS = ("agent_actions_taken", "agent_commitments", "caller_commitments")
CLAIM_ID = re.compile(r"\[CLAIM_\d+\]|\bCLM-\d{6}-\d{4}\b")


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    elif value:
        items = [value]
    else:
        return []
    return [str(item).strip() for item in items if str(item).strip()]


def _claim_ids(transcript: str) -> list[str]:
    found: list[str] = []
    for match in CLAIM_ID.findall(transcript):
        if match not in found:
            found.append(match)
    return found


def _topic_transcript(transcript: str, topic: str) -> str:
    topic_name = topic.removeprefix("topic_").replace("_", " ")
    instruction = (
        f"Focus only on the {topic_name} topic. "
        "Ignore evidence that belongs only to other topics."
    )
    return f"{instruction}\n\nTranscript:\n{transcript}"


async def _score(transcript: str, topic: str, client: Any) -> dict[str, float]:
    response = await client.system_one(
        _topic_transcript(transcript, topic),
        SCORER_QUESTIONS,
    )
    return {
        name: float(
            response.nouls[name].noul
            if question["type"] == "noul"
            else response.scores[name].score
        )
        for name, question in SCORER_QUESTIONS.items()
    }


async def _extract(transcript: str, topic: str, client: Any) -> dict[str, Any]:
    prompt = EXTRACTOR_TEMPLATE.replace(
        "{requested_fields}", json.dumps(REQUESTED_FIELDS)
    ).replace("{transcript}", _topic_transcript(transcript, topic))
    response = await client.chat.completions.create(
        model=GPT_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    extraction = json.loads(response.choices[0].message.content)
    extraction["claim_id"] = _claim_ids(transcript) or _as_list(extraction.get("claim_id"))
    for field in LIST_FIELDS:
        extraction[field] = [item[:MAX_LIST_ITEM_CHARS] for item in _as_list(extraction.get(field))]
    return extraction


async def _summarize(transcript: str, topic: str, client: Any) -> str:
    topic_name = topic.removeprefix("topic_").replace("_", " ")
    prompt = SUMMARIZER_TEMPLATE.replace("{topic}", topic_name).replace(
        "{transcript}",
        _topic_transcript(transcript, topic),
    )
    response = await client.chat.completions.create(
        model=GPT_MODEL,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return str(response.choices[0].message.content or "").strip()


async def process_topic(
    topic: str,
    transcript: str,
    scorer_client: Any,
    extractor_client: Any,
) -> dict[str, Any]:
    """Run Jev scoring plus GPT extraction and summary for one topic."""

    scores, extraction, summary = await asyncio.gather(
        _score(transcript, topic, scorer_client),
        _extract(transcript, topic, extractor_client),
        _summarize(transcript, topic, extractor_client),
    )
    extraction["summary"] = summary
    return {"scores": scores, "extraction": extraction}


async def _gather_topics(
    transcript: str,
    topics: list[str],
    scorer_client: Any,
    extractor_client: Any,
) -> dict[str, dict[str, Any]]:
    topics = list(dict.fromkeys(topics))
    gathered = await asyncio.gather(
        *(process_topic(topic, transcript, scorer_client, extractor_client) for topic in topics),
        return_exceptions=True,
    )
    results = {}
    for topic, result in zip(topics, gathered):
        if isinstance(result, Exception):
            logger.error("Failed to process %s: %s", topic, result, exc_info=result)
        else:
            results[topic] = result
    return results


async def process_topics(
    transcript: str,
    topics: list[str],
    *,
    scorer_client: Any | None = None,
    extractor_client: Any | None = None,
    api_key: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Process each selected topic independently."""

    if (scorer_client is None) != (extractor_client is None):
        logger.error("Provide both clients or neither client")
        raise ValueError("Provide both clients or neither client")

    try:
        if scorer_client is not None and extractor_client is not None:
            results = await _gather_topics(transcript, topics, scorer_client, extractor_client)
        else:
            from openai import AsyncOpenAI
            from typesafe_sdk import AsyncTypeSafeClient

            key = require_api_key(api_key)
            extractor = AsyncOpenAI(api_key=key, base_url=OPENAI_OPENROUTER_URL)
            try:
                async with AsyncTypeSafeClient(
                    api_key=key,
                    base_url=OPENROUTER_URL,
                    model=JEV_MODEL,
                ) as scorer:
                    results = await _gather_topics(transcript, topics, scorer, extractor)
            finally:
                await extractor.close()
    except Exception:
        logger.exception("Topic processing failed")
        raise

    logger.info("Processed %s topics: %s", len(results), ", ".join(results) or "none")
    return results
