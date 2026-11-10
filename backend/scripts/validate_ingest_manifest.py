"""Fail the daily refresh when the live corpus is incomplete or unusable."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.config import DEFAULT_EMBEDDING_MODEL
from app.services.registry import REQUIRED_GROWW_URLS

DEFAULT_MANIFEST = _BACKEND_DIR / "data" / "manifest.json"


def validate_manifest(manifest: dict, *, embedding_model: str = DEFAULT_EMBEDDING_MODEL) -> list[str]:
    """Return human-readable errors. An empty list means the corpus may be published."""
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest is not an object"]

    sources = manifest.get("sources")
    if not isinstance(sources, list):
        errors.append("manifest sources must be a list")
        sources = []

    by_url: dict[str, dict] = {}
    for entry in sources:
        if not isinstance(entry, dict):
            continue
        url = entry.get("url")
        if isinstance(url, str) and url:
            by_url[url] = entry

    for url in REQUIRED_GROWW_URLS:
        entry = by_url.get(url)
        if entry is None:
            errors.append(f"required Groww URL missing from manifest: {url}")
            continue
        if entry.get("status") != "ok":
            detail = entry.get("error") or entry.get("status") or "unknown error"
            errors.append(f"required Groww URL failed ({detail}): {url}")

    passage_count = manifest.get("passage_count")
    if not isinstance(passage_count, int) or passage_count <= 0:
        errors.append(f"passage_count must be a positive int, got {passage_count!r}")

    recorded_model = manifest.get("embedding_model")
    if recorded_model != embedding_model:
        errors.append(
            f"embedding_model must be {embedding_model!r}, got {recorded_model!r}"
        )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a live ingest manifest for publishing")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)

    try:
        payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"manifest not found: {args.manifest}", file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError) as exc:
        print(f"could not read manifest {args.manifest}: {exc}", file=sys.stderr)
        return 1

    errors = validate_manifest(payload)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(
        f"manifest ok: passage_count={payload.get('passage_count')} "
        f"embedding_model={payload.get('embedding_model')} "
        f"accessed_at={payload.get('accessed_at')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
