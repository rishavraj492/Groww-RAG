import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_TIMEOUT_SECONDS,
    EDUCATION_URLS,
    HOLDINGS_CAP,
    PASSAGE_CAP,
    QUESTION_MAX_LENGTH,
    RETRIEVAL_SCORE_FLOOR,
)
from app.main import create_app
from app.services.index import require_loaded_index
from app.services.index import require_loaded_index

FIXTURE_FACTS = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "scheme_facts.json"


def test_health_reports_loaded_fixture_facts(tmp_path):
    with TestClient(create_app(FIXTURE_FACTS, chroma_path=tmp_path / "chroma")) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "factsLoaded": True,
        "schemeCount": 2,
        "passageCount": 0,
        "embeddingModel": DEFAULT_EMBEDDING_MODEL,
        "oldestAccessedAt": "2026-10-31",
    }


def test_startup_refuses_a_different_embedding_model(tmp_path, caplog):
    _write_manifest(tmp_path, {"embedding_model": "other/model", "passage_count": 1})
    with caplog.at_level(logging.ERROR, logger="app.services.index"):
        with pytest.raises(SystemExit) as caught:
            require_loaded_index(tmp_path / "manifest.json", tmp_path / "chroma", DEFAULT_EMBEDDING_MODEL)
    assert caught.value.code == 1
    assert "scripts/ingest.py" in caplog.text


def test_startup_refuses_an_empty_index_when_the_manifest_lists_passages(tmp_path, caplog):
    _write_manifest(
        tmp_path,
        {"embedding_model": DEFAULT_EMBEDDING_MODEL, "passage_count": 4},
    )
    with caplog.at_level(logging.ERROR, logger="app.services.index"):
        with pytest.raises(SystemExit) as caught:
            require_loaded_index(
                tmp_path / "manifest.json",
                tmp_path / "missing-chroma",
                DEFAULT_EMBEDDING_MODEL,
            )
    assert caught.value.code == 1
    assert "empty" in caplog.text
    assert "scripts/ingest.py" in caplog.text


def test_health_reports_the_indexed_passage_count(tmp_path):
    from scripts.ingest import run_ingest
    from tests.fake_embedder import FakeEmbedder

    data = Path(__file__).resolve().parents[1] / "data"
    facts = tmp_path / "scheme_facts.json"
    chroma_path = tmp_path / "chroma"

    def reject():
        raise AssertionError("fixture ingest must not open an HTTP client")

    run_ingest(
        "fixture",
        sources_path=data / "sources.yaml",
        facts_path=facts,
        manifest_path=tmp_path / "manifest.json",
        fixtures_dir=data / "fixtures",
        accessed_at="2026-10-31",
        chroma_path=chroma_path,
        embedder=FakeEmbedder(model_name=DEFAULT_EMBEDDING_MODEL),
        client_factory=reject,
    )
    with TestClient(create_app(facts, chroma_path=chroma_path)) as client:
        body = client.get("/api/health").json()
    assert body["passageCount"] == 4
    assert body["embeddingModel"] == DEFAULT_EMBEDDING_MODEL
    assert body["factsLoaded"] is True


def test_phase0_limits_and_groq_defaults():
    assert QUESTION_MAX_LENGTH == 500
    assert PASSAGE_CAP == 4
    assert HOLDINGS_CAP == 10
    assert DEFAULT_LLM_TIMEOUT_SECONDS == 20
    assert DEFAULT_LLM_BASE_URL == "https://api.groq.com/openai/v1"
    assert DEFAULT_LLM_MODEL == "openai/gpt-oss-120b"
    assert DEFAULT_EMBEDDING_MODEL == "BAAI/bge-small-en-v1.5"
    assert isinstance(RETRIEVAL_SCORE_FLOOR, float)
    assert 0 < RETRIEVAL_SCORE_FLOOR < 2
    assert EDUCATION_URLS == (
        "https://www.amfiindia.com/investor",
        "https://investor.sebi.gov.in/",
        "https://groww.in/learn/mutual-funds",
    )


def _write_manifest(tmp_path: Path, payload: dict) -> None:
    (tmp_path / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
