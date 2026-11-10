"""Embed a question, filter the passage index, and apply the score floor."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import PASSAGE_CAP, RETRIEVAL_SCORE_FLOOR
from app.services.embeddings import QUERY_PREFIX, Embedder


@dataclass(frozen=True)
class Passage:
    text: str
    source_url: str
    title: str
    authority: str
    document_type: str
    scheme_id: str
    topic: str
    accessed_at: str
    as_of: str | None
    distance: float


def retrieve(
    question: str,
    *,
    embedder: Embedder,
    collection,
    scheme_id: str | None = None,
    topic: str | None = None,
    score_floor: float = RETRIEVAL_SCORE_FLOOR,
    limit: int = PASSAGE_CAP,
) -> list[Passage]:
    """Return up to `limit` passages. Drop the set when the best cosine distance is over the floor.

    `scheme_id` and `topic` filter when the resolver set them. An empty string is a
    real filter (general documents). Official passages are ordered ahead of platform ones.
    """
    total = int(collection.count())
    if total <= 0 or limit <= 0:
        return []
    vector = embedder.embed([QUERY_PREFIX + question])[0]
    result = collection.query(
        query_embeddings=[vector],
        n_results=min(limit, total),
        where=_where(scheme_id, topic),
        include=["documents", "metadatas", "distances"],
    )
    hits = _hits(result)
    if not hits:
        return []
    hits.sort(key=lambda hit: hit.distance)
    hits = hits[:limit]
    if min(hit.distance for hit in hits) > score_floor:
        return []
    hits.sort(key=lambda hit: (0 if hit.authority == "official" else 1, hit.distance))
    return hits


def _where(scheme_id: str | None, topic: str | None) -> dict | None:
    clauses: list[dict] = []
    if scheme_id is not None:
        clauses.append({"scheme_id": scheme_id})
    if topic is not None:
        clauses.append({"topic": topic})
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _hits(result: dict) -> list[Passage]:
    ids = result.get("ids") or []
    if not ids or not ids[0]:
        return []
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    hits: list[Passage] = []
    for text, metadata, distance in zip(documents, metadatas, distances):
        if text is None or distance is None:
            continue
        meta = metadata or {}
        hits.append(
            Passage(
                text=str(text),
                source_url=_text(meta.get("source_url")),
                title=_text(meta.get("title")),
                authority=_text(meta.get("authority")),
                document_type=_text(meta.get("document_type")),
                scheme_id=_text(meta.get("scheme_id")),
                topic=_text(meta.get("topic")),
                accessed_at=_text(meta.get("accessed_at")),
                as_of=_optional(meta.get("as_of")),
                distance=float(distance),
            )
        )
    return hits


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _optional(value: object) -> str | None:
    text = _text(value).strip()
    return text or None
