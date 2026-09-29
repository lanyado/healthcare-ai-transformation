"""Turn pipeline scores/extractions into the CRM UI shape. No raw scores."""

from __future__ import annotations

from typing import Any


def call_title(call_id: str) -> str:
    return call_id.replace("call_", "CALL-").upper()


def topic_label(topic_id: str) -> str:
    name = topic_id.removeprefix("topic_")
    return name.replace("_", " ").title()


def yes_no(score: Any) -> str:
    try:
        return "Yes" if float(score) >= 0.8 else "No"
    except (TypeError, ValueError):
        return "No"


def bucket(score: Any, labels: list[str]) -> str:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return labels[0]
    index = min(int(value * len(labels)), len(labels) - 1)
    return labels[index]


def as_list(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def metadata_rows(call: dict[str, Any]) -> list[list[str]]:
    crm = call.get("crm_context") or {}
    providers = crm.get("known_providers") or []
    seconds = int(call.get("duration_seconds") or 0)
    rows = [
        ["Agent ID", call.get("agent_id") or ""],
        ["Call date", call.get("call_date") or ""],
        ["Duration", f"{seconds // 60}m {seconds % 60:02d}s" if seconds else ""],
        ["Member", crm.get("member_name") or ""],
        ["Plan", crm.get("plan_name") or ""],
        ["Provider", providers[0] if providers else ""],
    ]
    return [row for row in rows if row[1]]


def present_topic(topic_id: str, result: dict[str, Any]) -> dict[str, Any]:
    scores = result.get("scores") or {}
    extraction = result.get("extraction") or {}
    fields = []
    claim_id = extraction.get("claim_id")
    claim_ids = claim_id if isinstance(claim_id, list) else ([claim_id] if claim_id else [])
    claim_ids = [str(item) for item in claim_ids if str(item).strip()]
    if claim_ids:
        fields.append({"label": "Claim ID", "value": ", ".join(claim_ids)})
    fields.extend(
        [
            {"label": "Resolved", "value": yes_no(scores.get("resolved"))},
            {"label": "Urgency", "value": bucket(scores.get("urgency"), ["None", "Low", "Moderate", "High", "Critical"])},
            {"label": "Sentiment", "value": bucket(scores.get("sentiment"), ["Strongly negative", "Negative", "Neutral", "Positive", "Strongly positive"])},
            {"label": "Compliance concern", "value": yes_no(scores.get("compliance_concern"))},
        ]
    )
    return {
        "id": topic_id,
        "label": topic_label(topic_id),
        "fields": fields,
        "agentActions": as_list(extraction.get("agent_actions_taken")),
        "agentCommitments": as_list(extraction.get("agent_commitments")),
        "callerCommitments": as_list(extraction.get("caller_commitments")),
        "summary": str(extraction.get("summary") or ""),
    }


def present_leg(call: dict[str, Any]) -> dict[str, Any]:
    transcript = call.get("transcript") or []
    text = "\n".join(transcript) if isinstance(transcript, list) else str(transcript)
    return {
        "id": call["call_id"],
        "callId": call_title(call["call_id"]),
        "label": call.get("title") or call_title(call["call_id"]),
        "metadata": {"agentId": call.get("agent_id") or "", "rows": metadata_rows(call)},
        "transcript": text,
    }


def present_crm(
    call: dict[str, Any],
    results: dict[str, dict[str, Any]],
    legs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    items = legs or [call]
    return {
        "id": call["call_id"],
        "callId": call_title(call["call_id"]),
        "label": call.get("title") or call_title(call["call_id"]),
        "patientId": call["member_id"],
        "metadata": {"agentId": call.get("agent_id") or "", "rows": metadata_rows(call)},
        "topics": [present_topic(topic_id, result) for topic_id, result in results.items()],
        "legs": [present_leg(item) for item in items],
    }
