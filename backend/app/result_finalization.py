"""Put real names and IDs back into model output."""

from __future__ import annotations

from typing import Any


def reassociate_entities(value: Any, entity_map: dict[str, dict[str, Any]]) -> Any:
    """Replace private placeholders with the real names and IDs."""

    if isinstance(value, str):
        for token, entity in entity_map.items():
            replacement = entity.get("canonical_name") or entity.get("canonical_id")
            if replacement:
                value = value.replace(token, replacement)
        return value
    if isinstance(value, list):
        return [reassociate_entities(item, entity_map) for item in value]
    if isinstance(value, dict):
        return {key: reassociate_entities(item, entity_map) for key, item in value.items()}
    return value
