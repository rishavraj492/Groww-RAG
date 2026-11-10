import os
from pathlib import Path

from dotenv import load_dotenv

QUESTION_MAX_LENGTH = 500
PASSAGE_CAP = 4
HOLDINGS_CAP = 10
ANSWER_MAX_SENTENCES = 4
ANSWER_MAX_CHARS = 800

# Cosine distance, lower is closer. Drop a retrieved set when its best distance
# is worse than this. Measured with BAAI/bge-small-en-v1.5 on the one-sentence
# mid-cap objective (0.26) and the other short fixture fields (at most 0.34).
# An unrelated question is about 0.57 or worse.
RETRIEVAL_SCORE_FLOOR = 0.45

EDUCATION_URLS = (
    "https://www.amfiindia.com/investor",
    "https://investor.sebi.gov.in/",
    "https://groww.in/learn/mutual-funds",
)

DEFAULT_LLM_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_LLM_MODEL = "openai/gpt-oss-120b"
DEFAULT_LLM_TIMEOUT_SECONDS = 20
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

# Groq base limits for openai/gpt-oss-120b.
LLM_REQUESTS_PER_MINUTE = 30
LLM_REQUESTS_PER_DAY = 1000
LLM_TOKENS_PER_MINUTE = 8000
LLM_TOKENS_PER_DAY = 200_000
# Includes reasoning tokens. Low effort plus this cap keeps one reply inside the minute budget.
LLM_MAX_COMPLETION_TOKENS = 1024
LLM_REASONING_EFFORT = "low"

_DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def parse_cors_origins(value: str | None) -> tuple[str, ...]:
    """Comma-separated browser origins. Empty / unset keeps local Vite defaults."""
    if value is None or not value.strip():
        return _DEFAULT_CORS_ORIGINS
    origins = tuple(
        origin.rstrip("/")
        for part in value.split(",")
        if (origin := part.strip())
    )
    return origins if origins else _DEFAULT_CORS_ORIGINS


_BACKEND_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_FACTS_PATH = _BACKEND_DIR / "data" / "fixtures" / "scheme_facts.json"
_DEFAULT_CHROMA_PATH = _BACKEND_DIR / "data" / "chroma"
_DEFAULT_FRONTEND_DIST = _BACKEND_DIR / "frontend_dist"
load_dotenv(_BACKEND_DIR / ".env")


def _env_path(name: str, default: Path) -> Path:
    value = os.getenv(name)
    if not value:
        return default
    path = Path(value)
    if not path.is_absolute():
        path = _BACKEND_DIR / path
    return path


LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", DEFAULT_LLM_BASE_URL)
LLM_MODEL = os.getenv("LLM_MODEL", DEFAULT_LLM_MODEL)
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", str(DEFAULT_LLM_TIMEOUT_SECONDS)))
FACTS_PATH = _env_path("FACTS_PATH", _DEFAULT_FACTS_PATH)
CHROMA_PATH = _env_path("CHROMA_PATH", _DEFAULT_CHROMA_PATH)
FRONTEND_DIST = _env_path("FRONTEND_DIST", _DEFAULT_FRONTEND_DIST)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
CORS_ORIGINS = parse_cors_origins(os.getenv("CORS_ORIGINS"))
