"""CRM lookup plus deterministic entity resolution and tokenization."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .config import TRANSCRIPTS_PATH

logger = logging.getLogger(__name__)


class PatientNotFoundError(LookupError):
    """The trusted member ID does not exist in the CRM."""


def patient_context_from_crm(patient_id: str, source: dict[str, Any]) -> dict[str, Any]:
    """Build the resolver CRM record from a stored call context."""

    names = source.get("known_providers", [""])
    claim_id = source.get("claim_id")
    auth_id = source.get("prior_authorization_id")
    return {
        "patient_id": patient_id,
        "member_name": source["member_name"],
        "plan_name": source["plan_name"],
        "known_providers": [
            {
                "provider_id": f"PRV-{index:03d}",
                "name": name,
                "organization": None if name.startswith("Dr.") else name,
            }
            for index, name in enumerate(source.get("known_providers", []), 1)
        ],
        "claims": (
            [
                {
                    "claim_id": claim_id,
                    "provider": names[0],
                    "status": "denied" if source.get("denial_code") else "processed",
                }
            ]
            if claim_id
            else []
        ),
        "prior_authorizations": (
            [
                {
                    "prior_authorization_id": auth_id,
                    "provider": names[-1],
                    "status": source.get("authorization_status", "active"),
                }
            ]
            if auth_id
            else []
        ),
        "known_contact_information": {
            "address": source.get("contact_record", {}).get("mailing_address"),
        },
    }


class FakeCRMHandler:
    """Build CRM records from the existing sample transcript data."""

    def __init__(self, data_path: Path | None = None) -> None:
        path = data_path or TRANSCRIPTS_PATH
        try:
            samples = json.loads(path.read_text())
        except Exception:
            logger.exception("Failed to load CRM samples from %s", path)
            raise
        self.samples = {sample["metadata"]["member_id"]: sample for sample in samples}

    def get_patient_context(self, patient_id: str) -> dict[str, Any]:
        patient_id = patient_id.strip().upper()
        if patient_id not in self.samples:
            logger.error("Unknown patient_id: %s", patient_id)
            raise PatientNotFoundError(f"Unknown patient_id: {patient_id}")
        return patient_context_from_crm(patient_id, self.samples[patient_id]["crm_context"])


@dataclass
class EntityResolutionResult:
    patient_id: str
    anonymized_transcript: str
    entity_map: dict[str, dict[str, Any]]
    crm_context: dict[str, Any]
    unresolved_entities: list[dict[str, Any]]


TOKEN_PREFIX = {
    "member": "MEMBER",
    "provider": "PROVIDER",
    "claim": "CLAIM",
    "prior_authorization": "PRIOR_AUTH",
    "phone_number": "PHONE",
    "address": "ADDRESS",
    "email": "EMAIL",
    "date_of_birth": "DOB",
}

PATTERNS = {
    "member": re.compile(r"\bHHP-\d{7}\b", re.IGNORECASE),
    "claim": re.compile(r"\bCLM-\d{6}-\d{4}\b", re.IGNORECASE),
    "prior_authorization": re.compile(r"\bPA-\d{5,}\b", re.IGNORECASE),
    "phone_number": re.compile(
        r"(?<!\w)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\w)"
    ),
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "address": re.compile(
        r"\b\d{1,6}\s+(?:[A-Z][\w'-]*\s+){0,5}"
        r"(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Drive|Dr\.?|Lane|Ln\.?|"
        r"Court|Ct\.?|Boulevard|Blvd\.?|Way)"
        r"(?:,\s*[A-Z][A-Za-z'-]*(?:\s+[A-Z][A-Za-z'-]*)*){0,2}"
        r"(?:\s+\d{5}(?:-\d{4})?)?\b",
        re.IGNORECASE,
    ),
}

PROVIDER_MENTION = re.compile(
    r"\b(?:Dr\.?|Doctor)\s+[A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+)?\b"
    r"|\b[A-Z][A-Za-z'-]{2,}\s+[A-Z][A-Za-z'-]{2,}\b"
)

DOB_MENTION = re.compile(
    r"(\b(?:date of birth|birthday)(?:(?:\s+is)?\s+|"
    r"[^\n]{0,80}\n(?:CALLER|AGENT):\s*))"
    r"((?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})",
    re.IGNORECASE,
)


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def _person_name(value: str) -> str:
    return re.sub(r"^(?:dr|doctor|mr|mrs|ms|miss)\s+", "", _normalize(value))


def _normalized_value(entity_type: str, value: str) -> str:
    if entity_type != "phone_number":
        return _normalize(value)
    digits = re.sub(r"\D", "", value)
    return digits[1:] if len(digits) == 11 and digits.startswith("1") else digits


def _member_aliases(name: str, patient_id: str) -> list[str]:
    aliases = [patient_id]
    parts = name.split()
    if name:
        aliases.append(name)
    if parts:
        aliases.append(parts[0])
        last = parts[-1]
        aliases.extend([f"Mr. {last}", f"Ms. {last}", f"Mrs. {last}", f"Miss {last}"])
    return [item for item in aliases if item]


def _provider_aliases(provider: dict[str, str]) -> list[str]:
    name = provider["name"]
    without_title = re.sub(r"^(?:Dr\.?|Doctor)\s+", "", name, flags=re.IGNORECASE)
    aliases = [name, without_title]
    if provider.get("organization"):
        aliases.append(provider["organization"])
    if len(without_title.split()) >= 2:
        last = without_title.split()[-1]
        aliases.extend([f"Dr. {last}", f"Dr {last}", f"Doctor {last}"])
    return list(dict.fromkeys(aliases))


def _crm_entities(context: dict[str, Any]) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []

    def add(
        entity_type: str,
        canonical_id: str,
        canonical_name: str | None,
        aliases: list[str],
    ) -> None:
        number = sum(entity["type"] == entity_type for entity in entities) + 1
        entities.append(
            {
                "type": entity_type,
                "token": f"[{TOKEN_PREFIX[entity_type]}_{number}]",
                "canonical_id": canonical_id,
                "canonical_name": canonical_name,
                "aliases": aliases,
                "source": "crm+transcript",
            }
        )

    add(
        "member",
        context["patient_id"],
        context["member_name"],
        _member_aliases(context["member_name"], context["patient_id"]),
    )
    for provider in context["known_providers"]:
        add("provider", provider["provider_id"], provider["name"], _provider_aliases(provider))
    for claim in context["claims"]:
        add("claim", claim["claim_id"], None, [claim["claim_id"]])
    for authorization in context["prior_authorizations"]:
        add("prior_authorization", authorization["prior_authorization_id"], None, [authorization["prior_authorization_id"]])
    contact = context["known_contact_information"]
    for entity_type, field in (
        ("phone_number", "phone"),
        ("address", "address"),
        ("email", "email"),
        ("date_of_birth", "date_of_birth"),
    ):
        if contact.get(field):
            add(entity_type, contact[field], None, [contact[field]])
    return entities


class _Registry:
    def __init__(self, entities: list[dict[str, Any]]) -> None:
        self.entities = entities
        self.entity_map: dict[str, dict[str, Any]] = {}
        self.unresolved: list[dict[str, Any]] = []
        self._unresolved: dict[tuple[str, str], str] = {}
        self._counts = {kind: sum(entity["type"] == kind for entity in entities) for kind in TOKEN_PREFIX}
        self._aliases: dict[str, list[dict[str, Any]]] = {}
        for entity in entities:
            for alias in entity["aliases"]:
                matches = self._aliases.setdefault(_normalize(alias), [])
                if entity not in matches:
                    matches.append(entity)
        self._providers = [entity for entity in entities if entity["type"] == "provider"]

    def record(self, entity: dict[str, Any], mention: str, confidence: float) -> str:
        entry = self.entity_map.setdefault(
            entity["token"],
            {
                "entity_type": entity["type"],
                "canonical_id": entity["canonical_id"],
                "canonical_name": entity["canonical_name"],
                "observed_mentions": [],
                "confidence": confidence,
                "source": entity["source"],
            },
        )
        if mention not in entry["observed_mentions"]:
            entry["observed_mentions"].append(mention)
        entry["confidence"] = min(entry["confidence"], confidence)
        return entity["token"]

    def mark_unresolved(self, mention: str, candidates: list[str]) -> str:
        key = ("provider", _normalize(mention))
        if key not in self._unresolved:
            token = f"[UNRESOLVED_PROVIDER_{len(self._unresolved) + 1}]"
            self._unresolved[key] = token
            self.unresolved.append(
                {
                    "token": token,
                    "mention": mention,
                    "entity_type": "provider",
                    "reason": "multiple plausible CRM providers",
                    "candidate_names": candidates,
                }
            )
        return self._unresolved[key]

    def replace_alias(self, match: re.Match[str]) -> str:
        mention = match.group()
        candidates = self._aliases[_normalize(mention)]
        if len(candidates) == 1:
            return self.record(candidates[0], mention, 1.0)
        names = [candidate["canonical_name"] for candidate in candidates if candidate["type"] == "provider"]
        return self.mark_unresolved(mention, names) if names else mention

    def replace_fuzzy_provider(self, match: re.Match[str]) -> str:
        mention = match.group()
        mention_name = _person_name(mention)
        scores = []
        for provider in self._providers:
            canonical_name = _person_name(provider["canonical_name"])
            if len(canonical_name.split()) < 2:
                continue
            full_score = SequenceMatcher(None, mention_name, canonical_name).ratio()
            last_name_score = SequenceMatcher(
                None, mention_name.split()[-1], canonical_name.split()[-1]
            ).ratio()
            titled = mention.lower().startswith(("dr", "doctor"))
            scores.append((max(full_score, last_name_score if titled else 0), provider))
        scores.sort(key=lambda item: item[0], reverse=True)
        if not scores or scores[0][0] < 0.78:
            return mention
        if len(scores) > 1 and scores[0][0] - scores[1][0] < 0.12:
            names = [
                provider["canonical_name"]
                for score, provider in scores
                if scores[0][0] - score < 0.12
            ]
            return self.mark_unresolved(mention, names)
        return self.record(scores[0][1], mention, round(scores[0][0], 2))

    def tokenize(self, entity_type: str, mention: str) -> str:
        value = _normalized_value(entity_type, mention)
        for entity in self.entities:
            if entity["type"] != entity_type:
                continue
            known = [entity["canonical_id"], *entity["aliases"]]
            if any(_normalized_value(entity_type, item) == value for item in known):
                return self.record(entity, mention, 1.0)
        self._counts[entity_type] += 1
        entity = {
            "type": entity_type,
            "token": f"[{TOKEN_PREFIX[entity_type]}_{self._counts[entity_type]}]",
            "canonical_id": mention,
            "canonical_name": None,
            "aliases": [mention],
            "source": "transcript",
        }
        self.entities.append(entity)
        return self.record(entity, mention, 1.0)


def _alias_pattern(entities: list[dict[str, Any]]) -> re.Pattern[str]:
    surfaces = {alias for entity in entities for alias in entity["aliases"]}
    return re.compile(
        r"(?<!\w)(?:"
        + "|".join(re.escape(alias).replace(r"\ ", r"\s+") for alias in sorted(surfaces, key=len, reverse=True))
        + r")(?!\w)",
        re.IGNORECASE,
    )


def resolve_and_anonymize(
    transcript: str,
    patient_id: str,
    crm_handler: Any,
) -> EntityResolutionResult:
    """Resolve and tokenize entities. This function never reads or writes Redis."""

    try:
        context = crm_handler.get_patient_context(patient_id)
        entities = _crm_entities(context)
        registry = _Registry(entities)
        anonymized = _alias_pattern(entities).sub(registry.replace_alias, transcript)
        anonymized = PROVIDER_MENTION.sub(registry.replace_fuzzy_provider, anonymized)
        for entity_type, pattern in PATTERNS.items():
            anonymized = pattern.sub(lambda match, kind=entity_type: registry.tokenize(kind, match.group()), anonymized)
        anonymized = DOB_MENTION.sub(
            lambda match: match.group(1) + registry.tokenize("date_of_birth", match.group(2)),
            anonymized,
        )
        if registry.unresolved:
            logger.warning(
                "Unresolved providers for %s: %s",
                context["patient_id"],
                len(registry.unresolved),
            )
        logger.info(
            "Resolved %s entities for %s",
            len(registry.entity_map),
            context["patient_id"],
        )
        return EntityResolutionResult(
            patient_id=context["patient_id"],
            anonymized_transcript=anonymized,
            entity_map=registry.entity_map,
            crm_context=context,
            unresolved_entities=registry.unresolved,
        )
    except PatientNotFoundError:
        raise
    except Exception:
        logger.exception("Entity resolution failed for %s", patient_id)
        raise
