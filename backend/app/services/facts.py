import json
import logging
from pathlib import Path

from app.schemas.facts import SchemeFact

logger = logging.getLogger(__name__)


def load_facts(path: Path | str) -> list[dict]:
    """Read a scheme facts file and return one record per scheme."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        schemes = payload.get("schemes", [])
    elif isinstance(payload, list):
        schemes = payload
    else:
        raise ValueError(f"scheme facts file must be a list or object: {path}")
    if not isinstance(schemes, list):
        raise ValueError(f"scheme facts file has no scheme list: {path}")
    return schemes


def get_scheme(facts: list[dict], scheme_id: str) -> dict | None:
    """Return the record for scheme_id, or None when it is absent."""
    for record in facts:
        if record.get("scheme_id") == scheme_id:
            return record
    return None


def require_facts(path: Path | str) -> list[dict]:
    """Load facts for the API. A missing file stops startup and names the ingest script."""
    facts_path = Path(path)
    if not facts_path.is_file():
        logger.error("Facts file not found at %s. Run python scripts/ingest.py", facts_path)
        raise SystemExit(1)
    return [SchemeFact.model_validate(record).model_dump() for record in load_facts(facts_path)]


def oldest_accessed_at(facts: list[dict]) -> str | None:
    """Earliest capture date on the loaded records."""
    dates = [str(record["accessed_at"]) for record in facts if record.get("accessed_at")]
    if not dates:
        return None
    return min(dates)
