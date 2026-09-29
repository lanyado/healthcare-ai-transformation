"""Small FastAPI app: enqueue call IDs, run workers, return saved CRM rows."""

from __future__ import annotations

import asyncio
import logging
import re
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .artifacts import get_recording, parse_byte_range, recording_info, seed_recordings
from .config import API_HOST, API_PORT
from .crm_handler import crm, write_crm_job
from .logging_setup import configure_logging
from .pipeline import run_extraction_job
from .present import present_crm
from .queue import (
    enqueue,
    finish_crm_job,
    finish_job,
    get_status,
    read_crm_job,
    read_job,
    retry_crm_job,
    retry_job,
)
from .transcript_relevance import custom_transcript_warning

configure_logging()
logger = logging.getLogger(__name__)

stop = threading.Event()
CALL_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def require_call_id(call_id: str) -> str:
    call_id = call_id.strip()
    if not CALL_ID.fullmatch(call_id):
        raise HTTPException(status_code=400, detail="Invalid call_id.")
    return call_id


class ExtractionRequest(BaseModel):
    call_id: str
    transcript: str | None = None
    member_id: str | None = None


class TranscriptCheckRequest(BaseModel):
    transcript: str


def extraction_worker() -> None:
    while not stop.is_set():
        try:
            job = read_job()
        except Exception:
            logger.exception("Could not read extraction:jobs")
            stop.wait(1)
            continue
        if job is None:
            continue
        message_id, call_id, attempts = job
        try:
            asyncio.run(run_extraction_job(call_id))
        except Exception:
            logger.exception("Extraction failed for %s (attempt %s)", call_id, attempts)
            finish_job(message_id)
            if retry_job(call_id, attempts):
                stop.wait(1)
            continue
        finish_job(message_id)


def crm_worker() -> None:
    while not stop.is_set():
        try:
            job = read_crm_job()
        except Exception:
            logger.exception("Could not read crm:jobs")
            stop.wait(1)
            continue
        if job is None:
            continue
        message_id, pointer = job
        try:
            write_crm_job(pointer)
        except Exception:
            logger.exception(
                "CRM write failed for %s (attempt %s)",
                pointer.get("interaction_id"),
                pointer.get("attempts"),
            )
            finish_crm_job(message_id)
            if retry_crm_job(pointer):
                stop.wait(1)
            continue
        finish_crm_job(message_id)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        crm.setup()
    except Exception:
        logger.exception("Could not seed PostgreSQL")
    try:
        seed_recordings()
    except Exception:
        logger.exception("Could not seed call recordings in S3")
    threading.Thread(target=extraction_worker, daemon=True).start()
    threading.Thread(target=crm_worker, daemon=True).start()
    yield
    stop.set()


app = FastAPI(title="Healthcare extraction", lifespan=lifespan)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/extractions")
def start_extraction(body: ExtractionRequest) -> dict[str, str]:
    call_id = require_call_id(body.call_id)
    if body.transcript is not None:
        transcript = body.transcript.strip()
        if not transcript:
            raise HTTPException(status_code=400, detail="Transcript is empty.")
        warning = custom_transcript_warning(transcript)
        if warning:
            raise HTTPException(status_code=400, detail=warning)
        member_id = (body.member_id or "").strip()
        if not member_id:
            raise HTTPException(status_code=400, detail="Member ID is required.")
        crm.save_call(call_id, member_id, transcript)
    elif not crm.load_call(call_id):
        raise HTTPException(status_code=404, detail=f"Unknown call_id: {call_id}")
    enqueue(call_id)
    return {"call_id": call_id, "status": "queued"}


@app.post("/api/transcripts/check")
def check_transcript(body: TranscriptCheckRequest) -> dict[str, str]:
    transcript = body.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript is empty.")
    warning = custom_transcript_warning(transcript)
    if warning:
        raise HTTPException(status_code=400, detail=warning)
    return {"status": "ok"}


@app.get("/api/recordings/{call_id}")
def play_recording(call_id: str, request: Request):
    call_id = require_call_id(call_id)
    try:
        size, _content_type = recording_info(call_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"No recording for {call_id}")
    span = parse_byte_range(request.headers.get("range"), size)
    start, end = span if span else (None, None)
    try:
        body, content_type, size = get_recording(call_id, start=start, end=end)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"No recording for {call_id}")
    if start is not None and end is not None:
        return StreamingResponse(
            body,
            status_code=206,
            media_type=content_type,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Range": f"bytes {start}-{end}/{size}",
                "Content-Length": str(end - start + 1),
            },
        )
    return StreamingResponse(
        body,
        media_type=content_type,
        headers={"Accept-Ranges": "bytes", "Content-Length": str(size)},
    )


@app.get("/api/extractions/{call_id}")
def get_extraction(call_id: str) -> dict:
    call_id = require_call_id(call_id)
    queued = get_status(call_id) or {}
    stored = crm.load_call(call_id)
    target_id = queued.get("merged_into") or (stored or {}).get("merged_into") or call_id
    chain = crm.load_call_chain(target_id)
    call = chain[0] if chain else stored
    if call is None:
        raise HTTPException(status_code=404, detail=f"Unknown call_id: {call_id}")
    target_queued = get_status(call["call_id"]) or queued
    results = crm.load_topic_results(call["call_id"])
    status = target_queued.get("status") or queued.get("status") or ("ready" if results else "idle")
    return {
        "call_id": call["call_id"],
        "status": status,
        "error": queued.get("error") or target_queued.get("error"),
        "merged_into": queued.get("merged_into") or (stored or {}).get("merged_into"),
        "crm": present_crm(call, results, chain) if results and status == "ready" else None,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.server:app", host=API_HOST, port=API_PORT)
