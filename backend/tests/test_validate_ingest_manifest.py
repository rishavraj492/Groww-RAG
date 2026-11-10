"""Offline checks for the Phase 8 ingest gate. No network and no model host."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import DEFAULT_EMBEDDING_MODEL
from app.services.registry import REQUIRED_GROWW_URLS
from scripts.validate_ingest_manifest import main, validate_manifest


def _ok_sources() -> list[dict]:
    return [
        {
            "url": url,
            "scheme_id": f"scheme-{index}",
            "document_type": "scheme_page",
            "authority": "platform",
            "status": "ok",
            "error": None,
        }
        for index, url in enumerate(REQUIRED_GROWW_URLS)
    ]


def test_validate_manifest_accepts_complete_live_corpus():
    manifest = {
        "accessed_at": "2026-11-10",
        "passage_count": 20,
        "embedding_model": DEFAULT_EMBEDDING_MODEL,
        "sources": _ok_sources()
        + [
            {
                "url": "https://www.amfiindia.com/investor",
                "scheme_id": "",
                "document_type": "regulatory",
                "authority": "official",
                "status": "failed",
                "error": "timeout",
            }
        ],
    }
    assert validate_manifest(manifest) == []


def test_validate_manifest_rejects_failed_required_groww_page():
    sources = _ok_sources()
    sources[0]["status"] = "failed"
    sources[0]["error"] = "timeout"
    errors = validate_manifest(
        {
            "passage_count": 20,
            "embedding_model": DEFAULT_EMBEDDING_MODEL,
            "sources": sources,
        }
    )
    assert any("required Groww URL failed" in error for error in errors)


def test_validate_manifest_rejects_zero_passages_or_wrong_model():
    base = {
        "sources": _ok_sources(),
        "passage_count": 0,
        "embedding_model": DEFAULT_EMBEDDING_MODEL,
    }
    assert any("passage_count" in error for error in validate_manifest(base))

    wrong_model = {
        "sources": _ok_sources(),
        "passage_count": 4,
        "embedding_model": "other-model",
    }
    assert any("embedding_model" in error for error in validate_manifest(wrong_model))


def test_validate_manifest_cli_reads_file(tmp_path: Path):
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "accessed_at": "2026-11-10",
                "passage_count": 12,
                "embedding_model": DEFAULT_EMBEDDING_MODEL,
                "sources": _ok_sources(),
            }
        ),
        encoding="utf-8",
    )
    assert main(["--manifest", str(path)]) == 0
    assert main(["--manifest", str(tmp_path / "missing.json")]) == 1
