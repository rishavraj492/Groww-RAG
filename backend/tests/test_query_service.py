"""Prose orchestration with a fake chat client. No live model and no embedding download."""

import json
import logging
import math
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import DEFAULT_LLM_MODEL
from app.main import create_app
from app.services.answer import UNAVAILABLE_TEXT
from app.services.embeddings import EMBEDDING_DIMENSIONS, QUERY_PREFIX
from app.services.facts import load_facts
from app.services.index import index_passages
from app.services.llm_client import LLMClient, LLMError
from app.services.prompt import SYSTEM_PROMPT
from app.services.query_service import answer_query
from tests.fake_embedder import FakeEmbedder

FIXTURE_FACTS = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "scheme_facts.json"
MID_URL = "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"
ELSS_URL = "https://www.amfiindia.com/investor"
HELP_URL = "https://groww.in/help/capital-gains-statement"
ELSS_TEXT = "ELSS schemes have a lock-in period of 3 years."
HELP_TEXT = "To download a capital gains statement, open the statements page and choose capital gains."
DISTRACTOR = "Chirag Setalvad is the current fund manager of a different indexed passage."
OBJECTIVE = (
    "Investment objective: To generate long-term capital appreciation from a portfolio "
    "invested predominantly in equity and equity related securities of mid-cap companies."
)
ELSS_QUESTION = "What is the ELSS lock-in period?"
STATEMENT_QUESTION = "How do I download a capital gains statement?"
EXPENSE_QUESTION = "What is the expense ratio of HDFC Mid Cap?"


class FakeClient:
    def __init__(self, content: object) -> None:
        self._content = content
        self.calls: list[dict[str, str]] = []

    def complete(self, *, system: str, user: str) -> str:
        self.calls.append({"system": system, "user": user})
        if isinstance(self._content, BaseException):
            raise self._content
        return str(self._content)


def test_elss_answer_cites_the_education_passage_and_omits_other_text(tmp_path, caplog):
    embedder = _close_embedder(ELSS_TEXT, DISTRACTOR)
    collection = index_passages(tmp_path / "chroma", [_elss_row(), _distractor_row()], embedder)
    client = FakeClient(_draft(ELSS_TEXT, [ELSS_URL]))
    facts = load_facts(FIXTURE_FACTS)
    with caplog.at_level(logging.INFO):
        response = answer_query(
            ELSS_QUESTION,
            None,
            facts,
            collection=collection,
            embedder=embedder,
            llm_client=client,
        )
    assert response.response_type == "factual"
    assert response.scheme is None
    assert response.answer == ELSS_TEXT
    assert [item.url for item in response.citations] == [ELSS_URL]
    assert response.citations[0].accessed_at == "2026-10-31"
    assert len(client.calls) == 1
    system = client.calls[0]["system"]
    user = client.calls[0]["user"]
    assert system == SYSTEM_PROMPT
    assert "only the supplied passages" in system
    assert "set grounded to false" in system
    assert "leave answer empty" in system
    assert "number, date, or name" in system
    assert "Do not recommend a scheme" in system
    assert "expected performance" in system
    assert "source_url" in system
    assert "JSON only" in system
    assert ELSS_QUESTION in user
    assert ELSS_TEXT in user
    assert f"source_url: {ELSS_URL}" in user
    assert "accessed_at: 2026-10-31" in user
    assert "authority: official" in user
    assert DISTRACTOR not in user
    assert DISTRACTOR not in system
    assert "0.74%" not in user
    assert "0.74%" not in system
    assert "Passage 2" not in user
    assert "supplied passages" not in caplog.text
    assert ELSS_TEXT not in caplog.text
    assert "outcome=retrieved" in caplog.text
    assert "modelLatencyMs=" in caplog.text


def test_statement_download_has_no_scheme(tmp_path):
    collection, embedder = _index(tmp_path, [_help_row()])
    client = FakeClient(_draft(HELP_TEXT, [HELP_URL]))
    response = answer_query(
        STATEMENT_QUESTION,
        "hdfc-mid-cap",
        load_facts(FIXTURE_FACTS),
        collection=collection,
        embedder=embedder,
        llm_client=client,
    )
    assert response.response_type == "factual"
    assert response.scheme is None
    assert response.answer == HELP_TEXT
    assert [item.url for item in response.citations] == [HELP_URL]
    assert len(client.calls) == 1


def test_expense_ratio_uses_the_fact_template_and_does_not_call_the_client(tmp_path):
    collection, embedder = _index(tmp_path, [_elss_row()])
    client = FakeClient(_draft(ELSS_TEXT, [ELSS_URL]))
    response = answer_query(
        EXPENSE_QUESTION,
        None,
        load_facts(FIXTURE_FACTS),
        collection=collection,
        embedder=embedder,
        llm_client=client,
    )
    assert client.calls == []
    assert response.response_type == "factual"
    assert response.scheme is not None
    assert response.scheme.id == "hdfc-mid-cap"
    assert response.answer == (
        "The expense ratio of HDFC Mid Cap Fund Direct Growth is 0.74%. "
        "Last updated from sources: 2026-10-31."
    )
    assert response.citations[0].url == MID_URL


def test_advice_personal_data_and_scheme_lock_in_do_not_call_the_client(tmp_path):
    collection, embedder = _index(tmp_path, [_elss_row()])
    facts = load_facts(FIXTURE_FACTS)
    client = FakeClient(_draft(ELSS_TEXT, [ELSS_URL]))
    advice = answer_query(
        "Should I invest in HDFC Mid Cap?",
        None,
        facts,
        collection=collection,
        embedder=embedder,
        llm_client=client,
    )
    personal = answer_query(
        "My PAN is ABCDE1234F. What is the ELSS lock-in period?",
        None,
        facts,
        collection=collection,
        embedder=embedder,
        llm_client=client,
    )
    lock_in = answer_query(
        "ELSS lock-in of HDFC Mid Cap",
        None,
        facts,
        collection=collection,
        embedder=embedder,
        llm_client=client,
    )
    assert client.calls == []
    assert advice.response_type == "refusal"
    assert personal.response_type == "refusal"
    assert lock_in.response_type == "factual"
    assert "Equity - Mid Cap" in lock_in.answer
    assert "3 years" not in lock_in.answer


def test_retrieval_below_the_floor_does_not_call_the_client(tmp_path):
    collection, embedder = _index(tmp_path, [_elss_row()])
    client = FakeClient(_draft(ELSS_TEXT, [ELSS_URL]))
    response = answer_query(
        "How do I bake sourdough bread at home?",
        None,
        load_facts(FIXTURE_FACTS),
        collection=collection,
        embedder=embedder,
        llm_client=client,
    )
    assert client.calls == []
    assert response.response_type == "unavailable"
    assert response.answer == UNAVAILABLE_TEXT
    assert ELSS_TEXT not in response.answer


def test_stray_percentage_unknown_citation_and_client_exception(tmp_path, caplog):
    collection, embedder = _index(tmp_path, [_elss_row()])
    facts = load_facts(FIXTURE_FACTS)
    stray = FakeClient(_draft("The lock-in period is 3 years and the fee is 12%.", [ELSS_URL]))
    stray_response = answer_query(
        ELSS_QUESTION,
        None,
        facts,
        collection=collection,
        embedder=embedder,
        llm_client=stray,
    )
    assert len(stray.calls) == 1
    assert stray_response.response_type == "unavailable"
    assert stray_response.answer == UNAVAILABLE_TEXT
    assert "12%" not in stray_response.answer
    assert ELSS_TEXT not in stray_response.answer

    dropped = FakeClient(_draft(ELSS_TEXT, ["https://evil.example/nope", ELSS_URL]))
    dropped_response = answer_query(
        ELSS_QUESTION,
        None,
        facts,
        collection=collection,
        embedder=embedder,
        llm_client=dropped,
    )
    assert dropped_response.response_type == "factual"
    assert dropped_response.answer == ELSS_TEXT
    assert [item.url for item in dropped_response.citations] == [ELSS_URL]

    broken = FakeClient(TimeoutError("timed out"))
    with caplog.at_level(logging.INFO):
        broken_response = answer_query(
            ELSS_QUESTION,
            None,
            facts,
            collection=collection,
            embedder=embedder,
            llm_client=broken,
        )
    assert broken_response.response_type == "unavailable"
    assert broken_response.answer == UNAVAILABLE_TEXT
    assert "timed out" not in broken_response.answer
    assert ELSS_TEXT not in caplog.text
    assert "modelLatencyMs=" in caplog.text

    invalid = FakeClient("not json")
    invalid_response = answer_query(
        ELSS_QUESTION,
        None,
        facts,
        collection=collection,
        embedder=embedder,
        llm_client=invalid,
    )
    assert invalid_response.response_type == "unavailable"
    assert invalid_response.answer == UNAVAILABLE_TEXT


def test_objective_question_returns_the_scheme_passage(tmp_path):
    collection, embedder = _index(
        tmp_path,
        [
            _row(
                OBJECTIVE,
                url=MID_URL,
                title="HDFC Mid Cap Fund Direct Growth",
                authority="platform",
                document_type="scheme_page",
                scheme_id="hdfc-mid-cap",
                topic="objective",
            )
        ],
    )
    answer = "The investment objective is long-term capital appreciation from mid-cap companies."
    client = FakeClient(_draft(answer, [MID_URL]))
    response = answer_query(
        "What is the investment objective of HDFC Mid Cap?",
        None,
        load_facts(FIXTURE_FACTS),
        collection=collection,
        embedder=embedder,
        llm_client=client,
    )
    assert response.response_type == "factual"
    assert response.scheme is not None
    assert response.scheme.id == "hdfc-mid-cap"
    assert response.answer == answer
    assert response.citations[0].url == MID_URL
    assert OBJECTIVE in client.calls[0]["user"]
    assert "0.74%" not in client.calls[0]["user"]


def test_api_returns_the_elss_passage_and_turns_a_client_error_into_http_200(tmp_path):
    collection, embedder = _index(tmp_path / "index", [_elss_row()])
    with TestClient(create_app(FIXTURE_FACTS, chroma_path=tmp_path / "empty")) as client:
        client.app.state.collection = collection
        client.app.state.embedder = embedder
        client.app.state.llm_client = FakeClient(_draft(ELSS_TEXT, [ELSS_URL]))
        ok = client.post("/api/query", json={"question": ELSS_QUESTION})
        client.app.state.llm_client = FakeClient(TimeoutError("timed out"))
        failed = client.post("/api/query", json={"question": ELSS_QUESTION})
    assert ok.status_code == 200
    body = ok.json()
    assert body["responseType"] == "factual"
    assert body["scheme"] is None
    assert body["answer"] == ELSS_TEXT
    assert body["citations"][0]["url"] == ELSS_URL
    assert body["citations"][0]["accessedAt"] == "2026-10-31"
    assert failed.status_code == 200
    assert failed.json()["responseType"] == "unavailable"
    assert ELSS_TEXT not in failed.json()["answer"]


def test_chat_client_posts_json_schema_at_temperature_zero():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{\"grounded\": true}"}}]})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http:
        client = LLMClient(
            api_key="secret-key",
            base_url="http://127.0.0.1:9/v1",
            model=DEFAULT_LLM_MODEL,
            timeout_seconds=20,
            http_client=http,
        )
        content = client.complete(system="system json", user="user json")
    assert content == '{"grounded": true}'
    assert seen["url"] == "http://127.0.0.1:9/v1/chat/completions"
    assert seen["authorization"] == "Bearer secret-key"
    assert seen["body"]["temperature"] == 0
    assert type(seen["body"]["temperature"]) is int
    assert seen["body"]["model"] == DEFAULT_LLM_MODEL
    assert seen["body"]["max_completion_tokens"] == 1024
    assert seen["body"]["reasoning_effort"] == "low"
    assert seen["body"]["reasoning_format"] == "hidden"
    assert seen["body"]["response_format"]["type"] == "json_schema"
    assert seen["body"]["response_format"]["json_schema"]["schema"]["required"] == [
        "grounded",
        "answer",
        "citation_urls",
    ]
    assert seen["body"]["messages"][0]["content"] == "system json"
    assert seen["body"]["messages"][1]["content"] == "user json"


def test_chat_client_hides_the_key_on_http_and_timeout_errors():
    def fail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "secret-key"})

    with httpx.Client(transport=httpx.MockTransport(fail)) as http:
        client = LLMClient(
            api_key="secret-key",
            base_url="http://127.0.0.1:9/v1",
            model=DEFAULT_LLM_MODEL,
            timeout_seconds=20,
            http_client=http,
        )
        with pytest.raises(LLMError) as caught:
            client.complete(system="system", user="user")
    assert "secret-key" not in str(caught.value)

    def time_out(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    with httpx.Client(transport=httpx.MockTransport(time_out)) as http:
        client = LLMClient(
            api_key="secret-key",
            base_url="http://127.0.0.1:9/v1",
            model=DEFAULT_LLM_MODEL,
            timeout_seconds=20,
            http_client=http,
        )
        with pytest.raises(LLMError) as caught:
            client.complete(system="system", user="user")
    assert "secret-key" not in str(caught.value)


def test_local_budget_stops_before_another_groq_call():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{\"grounded\": true}"}}], "usage": {"total_tokens": 20}},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = LLMClient(
            api_key="secret-key",
            base_url="http://127.0.0.1:9/v1",
            model=DEFAULT_LLM_MODEL,
            timeout_seconds=20,
            http_client=http,
            requests_per_minute=1,
            requests_per_day=1000,
            tokens_per_minute=8000,
            tokens_per_day=200_000,
            max_completion_tokens=32,
        )
        client.complete(system="system", user="user")
        with pytest.raises(LLMError) as caught:
            client.complete(system="system", user="user")
    assert calls["count"] == 1
    assert "secret-key" not in str(caught.value)
    assert "rate limit" in str(caught.value)


def test_token_budget_stops_before_the_request_is_sent():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("token budget should stop the request")

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = LLMClient(
            api_key="secret-key",
            base_url="http://127.0.0.1:9/v1",
            model=DEFAULT_LLM_MODEL,
            timeout_seconds=20,
            http_client=http,
            requests_per_minute=30,
            tokens_per_minute=50,
            max_completion_tokens=100,
        )
        with pytest.raises(LLMError) as caught:
            client.complete(system="system", user="user")
    assert "rate limit" in str(caught.value)


def test_query_service_tests_do_not_load_the_local_embedding_model():
    assert "sentence_transformers" not in sys.modules


def _index(path: Path, rows: list[dict]):
    embedder = FakeEmbedder()
    collection = index_passages(path / "chroma", rows, embedder)
    return collection, embedder


def _close_embedder(*texts: str):
    return _ScriptedEmbedder(_near(0.05), {text: _axis(0) for text in texts})


class _ScriptedEmbedder:
    def __init__(self, query_vector: list[float], passage_vectors: dict[str, list[float]]) -> None:
        self.query_vector = query_vector
        self.passage_vectors = passage_vectors

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            if text.startswith(QUERY_PREFIX):
                vectors.append(self.query_vector)
            else:
                vectors.append(self.passage_vectors[text])
        return vectors


def _axis(slot: int) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[slot] = 1.0
    return vector


def _near(distance: float) -> list[float]:
    similarity = 1.0 - distance
    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[0] = similarity
    vector[1] = math.sqrt(max(0.0, 1.0 - similarity * similarity))
    return vector


def _elss_row() -> dict:
    return _row(
        ELSS_TEXT,
        url=ELSS_URL,
        title="AMFI investor education",
        authority="official",
        document_type="regulatory",
        scheme_id="",
        topic="elss_lock_in",
    )


def _help_row() -> dict:
    return _row(
        HELP_TEXT,
        url=HELP_URL,
        title="Capital gains statement",
        authority="platform",
        document_type="help",
        scheme_id="",
        topic="statement_download",
    )


def _distractor_row() -> dict:
    return _row(
        DISTRACTOR,
        url=MID_URL,
        title="HDFC Mid Cap Fund Direct Growth",
        authority="platform",
        document_type="scheme_page",
        scheme_id="hdfc-mid-cap",
        topic="fund_manager",
    )


def _row(
    text: str,
    *,
    url: str,
    title: str,
    authority: str,
    document_type: str,
    scheme_id: str,
    topic: str,
) -> dict:
    return {
        "text": text,
        "source_url": url,
        "title": title,
        "authority": authority,
        "document_type": document_type,
        "scheme_id": scheme_id,
        "topic": topic,
        "accessed_at": "2026-10-31",
        "as_of": "",
    }


def _draft(answer: str, urls: list[str]) -> str:
    return json.dumps({"grounded": True, "answer": answer, "citation_urls": urls})
