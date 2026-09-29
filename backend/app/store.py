"""PostgreSQL tables: source calls and saved CRM topic results."""

from __future__ import annotations

import json
import logging
from typing import Any

import psycopg

from .artifacts import get_transcript, put_transcript
from .config import DATABASE_URL, RECONNECT_WINDOW_SECONDS, TRANSCRIPTS_PATH
from .entity_resolution import PatientNotFoundError, patient_context_from_crm

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS calls (
    call_id TEXT PRIMARY KEY,
    member_id TEXT NOT NULL,
    title TEXT NOT NULL,
    agent_id TEXT,
    call_date TEXT,
    duration_seconds INTEGER,
    crm_context JSONB NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    merged_into TEXT
);
CREATE TABLE IF NOT EXISTS crm_topic_results (
    interaction_id TEXT NOT NULL,
    patient_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    scores JSONB NOT NULL,
    extraction JSONB NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (interaction_id, topic)
);
"""


def connect():
    return psycopg.connect(DATABASE_URL)


def as_json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _call_row(row: tuple) -> dict[str, Any]:
    return {
        "call_id": row[0],
        "member_id": row[1],
        "title": row[2],
        "agent_id": row[3],
        "call_date": row[4],
        "duration_seconds": row[5],
        "crm_context": as_json(row[6]),
        "transcript": get_transcript(row[0]),
        "started_at": row[7],
        "merged_into": row[8] if len(row) > 8 else None,
    }


def _archive_replaced_call(cursor, call_id: str, new_lines: list[str]) -> None:
    """Keep the previous custom row so a callback within 5 minutes can still be found."""

    cursor.execute(
        """
        SELECT member_id, title, agent_id, call_date, duration_seconds,
               crm_context, started_at
        FROM calls WHERE call_id = %s
        """,
        (call_id,),
    )
    row = cursor.fetchone()
    if not row:
        return
    old_lines = get_transcript(call_id)
    if old_lines == new_lines:
        return
    started = row[6]
    stamp = int(started.timestamp()) if started else 0
    archive_id = f"{call_id}_{stamp}"
    put_transcript(archive_id, old_lines)
    cursor.execute(
        """
        INSERT INTO calls (
            call_id, member_id, title, agent_id, call_date,
            duration_seconds, crm_context, started_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (call_id) DO NOTHING
        """,
        (
            archive_id,
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
            json.dumps(as_json(row[5])),
            started,
        ),
    )


def setup() -> None:
    """Create tables and load data/transcripts.json into calls."""

    samples = json.loads(TRANSCRIPTS_PATH.read_text())
    with connect() as db:
        with db.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            cur.execute(
                "ALTER TABLE calls ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
            )
            cur.execute("ALTER TABLE calls ADD COLUMN IF NOT EXISTS merged_into TEXT")
            cur.execute("ALTER TABLE calls DROP COLUMN IF EXISTS transcript")
            for sample in samples:
                cur.execute(
                    """
                    INSERT INTO calls (
                        call_id, member_id, title, agent_id, call_date,
                        duration_seconds, crm_context
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (call_id) DO UPDATE SET
                        member_id = EXCLUDED.member_id,
                        title = EXCLUDED.title,
                        agent_id = EXCLUDED.agent_id,
                        call_date = EXCLUDED.call_date,
                        duration_seconds = EXCLUDED.duration_seconds,
                        crm_context = EXCLUDED.crm_context
                    """,
                    (
                        sample["id"],
                        sample["metadata"]["member_id"],
                        sample["title"],
                        sample["metadata"]["agent_id"],
                        sample["metadata"]["call_date"],
                        sample["metadata"]["duration_seconds"],
                        json.dumps(sample["crm_context"]),
                    ),
                )
        db.commit()
    for sample in samples:
        put_transcript(sample["id"], sample["transcript"])
    logger.info("Seeded %s calls", len(samples))


def save_call(call_id: str, member_id: str, transcript: str) -> None:
    """Insert or replace a custom call so the worker can load it like a sample."""

    lines = [line for line in transcript.splitlines() if line.strip()] or [transcript.strip()]
    member_id = member_id.strip() or "CUSTOM"
    crm_context = {"member_name": "", "plan_name": "", "known_providers": []}
    with connect() as db:
        with db.cursor() as cur:
            _archive_replaced_call(cur, call_id, lines)
            if member_id != "CUSTOM":
                cur.execute(
                    """
                    SELECT crm_context FROM calls
                    WHERE upper(member_id) = %s AND call_id <> %s
                    LIMIT 1
                    """,
                    (member_id.upper(), call_id),
                )
                row = cur.fetchone()
                if row:
                    crm_context = as_json(row[0])
            cur.execute(
                """
                INSERT INTO calls (
                    call_id, member_id, title, agent_id, call_date,
                    duration_seconds, crm_context
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (call_id) DO UPDATE SET
                    member_id = EXCLUDED.member_id,
                    crm_context = EXCLUDED.crm_context,
                    started_at = NOW(),
                    merged_into = NULL
                """,
                (
                    call_id,
                    member_id,
                    "Custom",
                    "",
                    "",
                    0,
                    json.dumps(crm_context),
                ),
            )
        db.commit()
    put_transcript(call_id, lines)
    logger.info("Saved custom call %s", call_id)


def load_call(call_id: str) -> dict[str, Any] | None:
    with connect() as db:
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT call_id, member_id, title, agent_id, call_date,
                       duration_seconds, crm_context, started_at, merged_into
                FROM calls WHERE call_id = %s
                """,
                (call_id,),
            )
            row = cur.fetchone()
    if not row:
        return None
    return _call_row(row)


def find_recent_call(member_id: str, exclude_call_id: str) -> dict[str, Any] | None:
    """Return the latest other call for this member inside the reconnect window."""

    member_id = member_id.strip()
    if not member_id or member_id.upper() == "CUSTOM":
        return None
    with connect() as db:
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT call_id, member_id, title, agent_id, call_date,
                       duration_seconds, crm_context, started_at, merged_into
                FROM calls
                WHERE upper(member_id) = %s
                  AND call_id <> %s
                  AND started_at >= NOW() - (%s * INTERVAL '1 second')
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (member_id.upper(), exclude_call_id, RECONNECT_WINDOW_SECONDS),
            )
            row = cur.fetchone()
    return _call_row(row) if row else None


def link_reconnect(call_id: str, root_id: str) -> None:
    with connect() as db:
        with db.cursor() as cur:
            cur.execute(
                "UPDATE calls SET merged_into = %s WHERE call_id = %s",
                (root_id, call_id),
            )
        db.commit()
    logger.info("Linked %s into %s", call_id, root_id)


def load_call_chain(call_id: str) -> list[dict[str, Any]]:
    """Root call plus every callback merged onto it, oldest first."""

    current = load_call(call_id)
    if current is None:
        return []
    root_id = current.get("merged_into") or current["call_id"]
    with connect() as db:
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT call_id, member_id, title, agent_id, call_date,
                       duration_seconds, crm_context, started_at, merged_into
                FROM calls
                WHERE call_id = %s OR merged_into = %s
                ORDER BY started_at ASC, call_id ASC
                """,
                (root_id, root_id),
            )
            rows = cur.fetchall()
    return [_call_row(row) for row in rows]


def load_topic_results(call_id: str) -> dict[str, dict[str, Any]]:
    with connect() as db:
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT topic, scores, extraction
                FROM crm_topic_results
                WHERE interaction_id = %s
                ORDER BY topic
                """,
                (call_id,),
            )
            rows = cur.fetchall()
    return {
        topic: {"scores": as_json(scores), "extraction": as_json(extraction)}
        for topic, scores, extraction in rows
    }


def save_crm_results(
    interaction_id: str,
    patient_id: str,
    results: dict[str, dict[str, Any]],
    *,
    connection=None,
) -> None:
    """Replace the stored topic rows for one call."""

    database = connection or connect()
    owns_connection = connection is None
    try:
        with database.cursor() as cursor:
            cursor.execute(
                "DELETE FROM crm_topic_results WHERE interaction_id = %s",
                (interaction_id,),
            )
            for topic, result in results.items():
                cursor.execute(
                    """
                    INSERT INTO crm_topic_results
                        (interaction_id, patient_id, topic, scores, extraction)
                    VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)
                    """,
                    (
                        interaction_id,
                        patient_id,
                        topic,
                        json.dumps(result["scores"]),
                        json.dumps(result["extraction"]),
                    ),
                )
        database.commit()
    except Exception:
        database.rollback()
        logger.exception("Failed to save CRM results for %s", interaction_id)
        raise
    finally:
        if owns_connection:
            database.close()
    logger.info("Saved CRM results for %s", interaction_id)


def get_patient_context(patient_id: str) -> dict[str, Any]:
    patient_id = patient_id.strip().upper()
    with connect() as db:
        with db.cursor() as cur:
            cur.execute(
                "SELECT crm_context FROM calls WHERE upper(member_id) = %s LIMIT 1",
                (patient_id,),
            )
            row = cur.fetchone()
    if not row:
        raise PatientNotFoundError(f"Unknown patient_id: {patient_id}")
    return patient_context_from_crm(patient_id, as_json(row[0]))
