"""Shared settings used by the live backend modules."""

from __future__ import annotations

import logging
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
PROMPTS_DIR = ROOT / "prompts"

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

JEV_MODEL = "~typesafe/jev-latest"
GPT_MODEL = "~openai/gpt-sol-latest"
OPENROUTER_URL = "https://openrouter.ai/api"
OPENAI_OPENROUTER_URL = "https://openrouter.ai/api/v1"
TOPIC_THRESHOLD = 0.80
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://healthcare:healthcare@localhost:5432/healthcare",
)
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:9000")
S3_BUCKET = os.getenv("S3_BUCKET", "healthcare")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minio")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minio123")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
SCHEMA_VERSION = "1.0"
DEFAULT_TTL_SECONDS = 5 * 60
MAX_JOB_ATTEMPTS = 3
REQUESTED_FIELDS = [
    "claim_id",
    "agent_actions_taken",
    "agent_commitments",
    "caller_commitments",
]
TRANSCRIPTS_PATH = REPO_ROOT / "data" / "transcripts.json"
TOPIC_PROMPT_PATH = PROMPTS_DIR / "topic_classifier.json"
RELEVANCE_PROMPT_PATH = PROMPTS_DIR / "relevance.json"
RELEVANCE_THRESHOLD = 0.80
SCORER_PROMPT_PATH = PROMPTS_DIR / "scorer.json"
EXTRACTOR_PROMPT_PATH = PROMPTS_DIR / "extractor.txt"
SUMMARIZER_PROMPT_PATH = PROMPTS_DIR / "summarizer.txt"
RECONNECT_PROMPT_PATH = PROMPTS_DIR / "reconnect.txt"
RECONNECT_WINDOW_SECONDS = 5 * 60
LOG_PATH = ROOT / "logs" / "backend.log"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def require_api_key(api_key: str | None = None) -> str:
    api_key = api_key or os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logging.getLogger(__name__).error("OPENROUTER_API_KEY is required")
        raise ValueError("OPENROUTER_API_KEY is required")
    return api_key
