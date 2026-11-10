"""Turn a question into the query API payload. Refusals do not read scheme facts."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from app.config import PASSAGE_CAP
from app.schemas.response import CitationModel, QueryResponse, SchemeRef
from app.services.answer import StructuredAnswer, render, render_refusal
from app.services.classify import ADVISORY, FACTUAL, PII, classify
from app.services.embeddings import Embedder
from app.services.guard import guard
from app.services.prompt import build_prompt
from app.services.registry import SCHEMES, SCHEME_BY_ID
from app.services.resolve import Resolution, resolve
from app.services.retrieve import Passage, retrieve

logger = logging.getLogger(__name__)

_SCHEME_FACT_KINDS = {"field", "holdings", "scheme_lock_in"}
_GENERAL_PROSE = {"definition", "elss_lock_in", "statement_download"}
_PROSE_KINDS = _GENERAL_PROSE | {"prose", "unknown"}


def answer_query(
    question: str,
    prior_scheme_id: str | None,
    facts: list[dict],
    *,
    collection=None,
    embedder: Embedder | None = None,
    embedder_factory: Callable[[], Embedder] | None = None,
    llm_client=None,
) -> QueryResponse:
    """Classify first. Personal-data and advice questions never read a scheme record or call a model."""
    query_type = classify(question)
    if query_type in {PII, ADVISORY}:
        rendered = render_refusal(query_type)
        response = _to_response(query_type, rendered)
        _log(query_type, rendered.scheme_ids, "refused")
        return response

    resolution = resolve(question, prior_scheme_id)
    if _needs_clarification(resolution):
        rendered = StructuredAnswer(
            response_type="unavailable",
            answer=_clarification_text(),
            scheme_ids=(),
            citations=(),
        )
        response = _to_response(FACTUAL, rendered)
        _log(FACTUAL, rendered.scheme_ids, "unavailable")
        return response

    if resolution.kind in _SCHEME_FACT_KINDS or resolution.ambiguous:
        rendered = render(facts, resolution)
        response = _to_response(FACTUAL, rendered)
        outcome = "structured" if response.response_type == "factual" else "unavailable"
        _log(FACTUAL, rendered.scheme_ids, outcome)
        return response

    if resolution.kind in _PROSE_KINDS:
        return _answer_prose(
            question,
            facts,
            resolution,
            collection=collection,
            embedder=embedder,
            embedder_factory=embedder_factory,
            llm_client=llm_client,
        )

    rendered = render(facts, resolution)
    response = _to_response(FACTUAL, rendered)
    _log(FACTUAL, rendered.scheme_ids, "unavailable")
    return response


def _answer_prose(
    question: str,
    facts: list[dict],
    resolution: Resolution,
    *,
    collection,
    embedder: Embedder | None,
    embedder_factory: Callable[[], Embedder] | None,
    llm_client,
) -> QueryResponse:
    passages = _retrieve_passages(
        question,
        resolution,
        collection=collection,
        embedder=embedder,
        embedder_factory=embedder_factory,
    )
    if not passages or llm_client is None:
        _log(FACTUAL, resolution.scheme_ids, "unavailable")
        return _unavailable(facts, resolution)

    system, user = build_prompt(question, passages)
    started = time.perf_counter()
    try:
        raw = llm_client.complete(system=system, user=user)
    except Exception:
        _log(FACTUAL, resolution.scheme_ids, "unavailable", _latency_ms(started))
        return _unavailable(facts, resolution)
    latency_ms = _latency_ms(started)
    grounded = guard(raw, passages)
    if grounded is None:
        _log(FACTUAL, resolution.scheme_ids, "unavailable", latency_ms)
        return _unavailable(facts, resolution)

    rendered = StructuredAnswer(
        response_type="factual",
        answer=grounded.answer,
        scheme_ids=_known_schemes(resolution),
        citations=grounded.citations,
    )
    response = _to_response(FACTUAL, rendered)
    _log(FACTUAL, rendered.scheme_ids, "retrieved", latency_ms)
    return response


def _retrieve_passages(
    question: str,
    resolution: Resolution,
    *,
    collection,
    embedder: Embedder | None,
    embedder_factory: Callable[[], Embedder] | None,
) -> list[Passage]:
    if collection is None or int(collection.count()) <= 0:
        return []
    active = embedder if embedder is not None else None
    if active is None and embedder_factory is not None:
        active = embedder_factory()
    if active is None:
        return []
    found: list[Passage] = []
    seen: set[tuple[str, str]] = set()
    for scheme_id, topic in _filters(resolution):
        hits = retrieve(
            question,
            embedder=active,
            collection=collection,
            scheme_id=scheme_id,
            topic=topic,
        )
        for hit in hits:
            key = (hit.source_url, hit.text)
            if key in seen:
                continue
            seen.add(key)
            found.append(hit)
    found.sort(key=lambda hit: (0 if hit.authority == "official" else 1, hit.distance))
    return found[:PASSAGE_CAP]


def _filters(resolution: Resolution) -> list[tuple[str | None, str | None]]:
    topic = resolution.topic
    if resolution.kind in _GENERAL_PROSE:
        return [("", topic)]
    if resolution.scheme_ids:
        return [(scheme_id, topic) for scheme_id in resolution.scheme_ids]
    if topic:
        return [(None, topic)]
    return [(None, None)]


def _known_schemes(resolution: Resolution) -> tuple[str, ...]:
    return tuple(scheme_id for scheme_id in resolution.scheme_ids if scheme_id in SCHEME_BY_ID)


def _unavailable(facts: list[dict], resolution: Resolution) -> QueryResponse:
    rendered = render(facts, resolution)
    response = _to_response(FACTUAL, rendered)
    return response


def _needs_clarification(resolution: Resolution) -> bool:
    return resolution.kind in _SCHEME_FACT_KINDS and not resolution.scheme_ids and not resolution.ambiguous


def _clarification_text() -> str:
    names = [scheme.name for scheme in SCHEMES]
    listed = ", ".join(names[:-1]) + ", or " + names[-1]
    return f"Which scheme do you mean? I can answer for {listed}."


def _to_response(query_type: str, rendered: StructuredAnswer) -> QueryResponse:
    scheme = None
    if len(rendered.scheme_ids) == 1:
        known = SCHEME_BY_ID[rendered.scheme_ids[0]]
        scheme = SchemeRef(id=known.scheme_id, name=known.name)
    return QueryResponse(
        response_type=rendered.response_type,
        query_type=query_type,
        answer=rendered.answer,
        scheme=scheme,
        citations=[
            CitationModel(
                url=item.url,
                title=item.title,
                authority=item.authority,
                accessed_at=item.accessed_at,
                as_of=item.as_of,
            )
            for item in rendered.citations
        ],
    )


def _latency_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


def _log(
    query_type: str,
    scheme_ids: tuple[str, ...],
    outcome: str,
    latency_ms: float | None = None,
) -> None:
    """Log the label, scheme id, outcome, and model latency. Never the prompt or an API key."""
    if latency_ms is None:
        logger.info(
            "queryType=%s schemeId=%s outcome=%s",
            query_type,
            ",".join(scheme_ids),
            outcome,
        )
        return
    logger.info(
        "queryType=%s schemeId=%s outcome=%s modelLatencyMs=%.0f",
        query_type,
        ",".join(scheme_ids),
        outcome,
        latency_ms,
    )
