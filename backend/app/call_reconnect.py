"""Merge a callback onto the previous call when the drop was under 5 minutes ago."""

from __future__ import annotations

import json
import logging
from typing import Any

from .config import GPT_MODEL, OPENAI_OPENROUTER_URL, RECONNECT_PROMPT_PATH, require_api_key
from .crm_handler import crm

logger = logging.getLogger(__name__)
RECONNECT_PROMPT = RECONNECT_PROMPT_PATH.read_text()


def as_lines(transcript: list[str] | str) -> list[str]:
    if isinstance(transcript, list):
        return [line for line in transcript if str(line).strip()]
    return [line for line in str(transcript).splitlines() if line.strip()]


def combined_transcript(calls: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for call in calls:
        lines.extend(as_lines(call.get("transcript") or []))
    return lines


def is_continuation(previous: str, current: str, *, client: Any | None = None) -> bool:
    """Ask GPT whether the current transcript continues the previous one after a drop."""

    prompt = RECONNECT_PROMPT.replace("{previous}", previous).replace("{current}", current)
    try:
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=require_api_key(), base_url=OPENAI_OPENROUTER_URL)
        response = client.chat.completions.create(
            model=GPT_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(response.choices[0].message.content or "{}")
        return bool(data.get("is_continuation"))
    except Exception:
        logger.exception("Reconnect check failed")
        return False


def _as_root(root: dict[str, Any], calls: list[dict[str, Any]]) -> dict[str, Any]:
    merged = dict(root)
    merged["transcript"] = combined_transcript(calls)
    return merged


def merge_reconnect(call: dict[str, Any], *, client: Any | None = None) -> dict[str, Any] | None:
    """If this is a callback continuation, link it to the previous call and return the combined root."""

    if call.get("merged_into"):
        root = crm.load_call(call["merged_into"])
        chain = crm.load_call_chain(call["merged_into"]) if root else []
        return _as_root(root, chain) if root and chain else None

    previous = crm.find_recent_call(call["member_id"], call["call_id"])
    if previous is None:
        return None

    root_id = previous.get("merged_into") or previous["call_id"]
    root = previous if root_id == previous["call_id"] else crm.load_call(root_id) or previous
    current_lines = as_lines(call["transcript"])
    previous_lines = as_lines(previous["transcript"])
    current_text = "\n".join(current_lines)
    previous_text = "\n".join(previous_lines)
    if not current_text or current_text in previous_text:
        return None
    if not is_continuation(previous_text, current_text, client=client):
        return None

    crm.link_reconnect(call["call_id"], root["call_id"])
    chain = crm.load_call_chain(root["call_id"])
    if not any(item["call_id"] == call["call_id"] for item in chain):
        chain = [*chain, call]
    logger.info("Merged %s into previous call %s", call["call_id"], root["call_id"])
    return _as_root(root, chain)
