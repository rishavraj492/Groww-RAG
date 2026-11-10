import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.answer import ADVISORY_REFUSAL, PII_REFUSAL
from app.services.facts import require_facts
from app.services.registry import SCHEMES

FIXTURE_FACTS = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "scheme_facts.json"
MID_URL = "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"
SMALL_URL = "https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth"
EXIT_LOAD = (
    "The exit load of HDFC Mid Cap Fund Direct Growth is 1% if redeemed within 1 year. "
    "Last updated from sources: 2026-10-31."
)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(FIXTURE_FACTS, chroma_path=tmp_path / "chroma")) as test_client:
        yield test_client


def test_empty_question_is_rejected(client):
    response = client.post("/api/query", json={"question": "   "})
    assert response.status_code == 422


def test_question_over_500_characters_is_rejected(client):
    response = client.post("/api/query", json={"question": "a" * 501})
    assert response.status_code == 422


def test_unknown_prior_scheme_is_rejected(client):
    response = client.post(
        "/api/query",
        json={"question": "What is the exit load?", "priorSchemeId": "not-a-scheme"},
    )
    assert response.status_code == 422


def test_mid_cap_exit_load_matches_the_fixture(client):
    response = client.post(
        "/api/query",
        json={"question": "What is the exit load of HDFC Mid Cap?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["responseType"] == "factual"
    assert body["queryType"] == "factual"
    assert body["answer"] == EXIT_LOAD
    assert body["scheme"] == {"id": "hdfc-mid-cap", "name": "HDFC Mid Cap Fund Direct Growth"}
    assert body["citations"] == [
        {
            "url": MID_URL,
            "title": "HDFC Mid Cap Fund Direct Growth",
            "authority": "platform",
            "accessedAt": "2026-10-31",
            "asOf": None,
        }
    ]


def test_advice_refuses_without_reading_scheme_values(client, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("scheme facts were read")

    monkeypatch.setattr("app.services.answer.get_scheme", boom)
    monkeypatch.setattr("app.services.facts.load_facts", boom)
    response = client.post("/api/query", json={"question": "Should I invest in HDFC Mid Cap?"})
    assert response.status_code == 200
    body = response.json()
    assert body["responseType"] == "refusal"
    assert body["queryType"] == "advisory"
    assert body["answer"] == ADVISORY_REFUSAL
    assert body["scheme"] is None
    assert "0.74%" not in body["answer"]
    assert "₹" not in body["answer"]
    assert any(item["url"] == "https://www.amfiindia.com/investor" for item in body["citations"])


def test_personal_data_is_refused_and_not_logged(client, caplog):
    pan = "ABCDE1234F"
    with caplog.at_level(logging.INFO):
        response = client.post(
            "/api/query",
            json={"question": f"My PAN is {pan}. What is the exit load of HDFC Mid Cap?"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["responseType"] == "refusal"
    assert body["queryType"] == "pii"
    assert body["answer"] == PII_REFUSAL
    assert body["scheme"] is None
    assert pan not in body["answer"]
    assert "0.74%" not in body["answer"]
    assert pan not in caplog.text
    assert "LLM_API_KEY" not in caplog.text


def test_null_field_is_unavailable(client):
    response = client.post(
        "/api/query",
        json={"question": "What is the expense ratio of HDFC Small Cap?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["responseType"] == "unavailable"
    assert body["queryType"] == "factual"
    assert body["scheme"]["id"] == "hdfc-small-cap"
    assert body["citations"][0]["url"] == SMALL_URL
    assert "0.74%" not in body["answer"]
    assert not any(char.isdigit() for char in body["answer"])


def test_field_question_without_a_scheme_lists_the_five_names(client):
    response = client.post("/api/query", json={"question": "What is the expense ratio?"})
    assert response.status_code == 200
    body = response.json()
    assert body["responseType"] == "unavailable"
    assert body["queryType"] == "factual"
    assert body["scheme"] is None
    assert body["citations"] == []
    for scheme in SCHEMES:
        assert scheme.name in body["answer"]
    assert "0.74" not in body["answer"]
    assert "₹" not in body["answer"]


def test_prior_scheme_answers_the_follow_up(client):
    response = client.post(
        "/api/query",
        json={"question": "and the exit load?", "priorSchemeId": "hdfc-mid-cap"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["responseType"] == "factual"
    assert body["answer"] == EXIT_LOAD
    assert body["scheme"]["id"] == "hdfc-mid-cap"
    assert body["citations"][0]["url"] == MID_URL


def test_schemes_lists_ids_names_and_urls_only(client):
    response = client.get("/api/schemes")
    assert response.status_code == 200
    body = response.json()
    assert [item["scheme_id"] for item in body] == [scheme.scheme_id for scheme in SCHEMES]
    for item in body:
        assert set(item) == {"scheme_id", "name", "url"}
        assert "expense_ratio" not in item
        assert "0.74%" not in str(item)


def test_missing_facts_file_exits_and_names_ingest(tmp_path, caplog):
    missing = tmp_path / "scheme_facts.json"
    with caplog.at_level(logging.ERROR, logger="app.services.facts"):
        with pytest.raises(SystemExit) as caught:
            require_facts(missing)
    assert caught.value.code == 1
    assert "scripts/ingest.py" in caplog.text


def test_empty_index_prose_stays_unavailable(client, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("empty index must not retrieve or call the model")

    monkeypatch.setattr("app.services.retrieve.retrieve", boom)
    monkeypatch.setattr("app.services.llm_client.LLMClient.complete", boom)
    response = client.post("/api/query", json={"question": "What is the ELSS lock-in?"})
    assert response.status_code == 200
    body = response.json()
    assert body["responseType"] == "unavailable"
    assert body["queryType"] == "factual"
    assert "don’t have that in the sources" in body["answer"]
    assert "three" not in body["answer"].lower()

    response = client.post(
        "/api/query",
        json={"question": "What is the investment objective of HDFC Mid Cap?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["responseType"] == "unavailable"
    assert "don’t have that in the sources" in body["answer"]
    assert "mid-cap companies" not in body["answer"]
