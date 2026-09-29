"""CRM handler: the only Postgres door for lookups and topic writes."""

from __future__ import annotations

import logging
from typing import Any

from . import store
from .artifacts import crm_rows, get_result
from .present import present_crm
from .queue import set_status

logger = logging.getLogger(__name__)


class PostgresCRMHandler:
    """All PostgreSQL reads and writes for calls and CRM topic rows."""

    def setup(self) -> None:
        store.setup()

    def save_call(self, call_id: str, member_id: str, transcript: str) -> None:
        store.save_call(call_id, member_id, transcript)

    def load_call(self, call_id: str) -> dict[str, Any] | None:
        return store.load_call(call_id)

    def load_call_chain(self, call_id: str) -> list[dict[str, Any]]:
        return store.load_call_chain(call_id)

    def find_recent_call(self, member_id: str, exclude_call_id: str) -> dict[str, Any] | None:
        return store.find_recent_call(member_id, exclude_call_id)

    def link_reconnect(self, call_id: str, root_id: str) -> None:
        store.link_reconnect(call_id, root_id)

    def load_topic_results(self, call_id: str) -> dict[str, dict[str, Any]]:
        return store.load_topic_results(call_id)

    def save_results(
        self,
        interaction_id: str,
        patient_id: str,
        results: dict[str, dict[str, Any]],
        *,
        connection=None,
    ) -> None:
        store.save_crm_results(
            interaction_id,
            patient_id,
            results,
            connection=connection,
        )

    def get_patient_context(self, patient_id: str) -> dict[str, Any]:
        return store.get_patient_context(patient_id)


crm = PostgresCRMHandler()


def write_crm_job(
    pointer: dict[str, Any],
    redis=None,
    s3=None,
    connection=None,
    handler: PostgresCRMHandler | None = None,
) -> dict[str, Any]:
    call_id = pointer["interaction_id"]
    db = handler or crm
    try:
        artifact = get_result(pointer["result_uri"], s3=s3)
        if artifact["schema_version"] != pointer.get("schema_version", artifact["schema_version"]):
            raise ValueError("schema_version on the CRM job does not match result.json")
        rows = crm_rows(artifact)
        db.save_results(
            artifact["interaction_id"],
            artifact["patient_id"],
            rows,
            connection=connection,
        )
        chain = db.load_call_chain(call_id)
        call = chain[0] if chain else db.load_call(call_id)
        if call is None:
            raise LookupError(f"Unknown call_id: {call_id}")
        presented = present_crm(call, rows, chain)
        set_status(call_id, "ready", {"crm": presented}, redis=redis)
        logger.info("Wrote CRM fields for %s", call_id)
        return presented
    except Exception:
        logger.exception("CRM write failed for %s", call_id)
        set_status(call_id, "error", {"error": "Could not save the CRM result."}, redis=redis)
        raise
