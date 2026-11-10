"""Deterministic embedder for tests. Does not load BAAI/bge-small-en-v1.5.

A question is placed near the indexed passage with the strongest token overlap,
at a fixed cosine distance, or far from every passage when the overlap is weak.
Distances sit on either side of ``RETRIEVAL_SCORE_FLOOR``.
"""

from __future__ import annotations

import hashlib
import math
import re

from app.services.embeddings import EMBEDDING_DIMENSIONS, QUERY_PREFIX

MATCH_DISTANCE = 0.05
MISS_DISTANCE = 0.95
MATCH_RECALL = 0.45

_STOPWORDS = frozenset(
    """
    a an the of to and or in on for from is are was were be been being
    what how do does did i we you this that with by as at it its if
    will can about into over than then so not no yes
    """.split()
)


class FakeEmbedder:
    def __init__(self, model_name: str = "fake-hash") -> None:
        self.model_name = model_name
        self.seen: list[str] = []
        self._passages: dict[str, list[float]] = {}

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            self.seen.append(text)
            if text.startswith(QUERY_PREFIX):
                vectors.append(self._query_vector(text[len(QUERY_PREFIX) :]))
            else:
                vector = _unit_vector(text)
                self._passages[text] = vector
                vectors.append(vector)
        return vectors

    def _query_vector(self, question: str) -> list[float]:
        if not self._passages:
            return _unit_vector(question)
        query_tokens = set(_content_tokens(question))
        best_text = ""
        best_recall = -1.0
        for text in self._passages:
            recall = _recall(query_tokens, set(_content_tokens(text)))
            if recall > best_recall:
                best_recall = recall
                best_text = text
        distance = MATCH_DISTANCE if best_recall >= MATCH_RECALL else MISS_DISTANCE
        return _at_distance(self._passages[best_text], distance, question)


def _content_tokens(text: str) -> list[str]:
    normalized = text.casefold().replace("-", " ")
    return [
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if token not in _STOPWORDS and len(token) > 1
    ]


def _recall(query: set[str], passage: set[str]) -> float:
    if not query:
        return 0.0
    return len(query & passage) / len(query)


def _unit_vector(text: str) -> list[float]:
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    counter = 0
    while len(values) < EMBEDDING_DIMENSIONS:
        block = hashlib.sha256(seed + counter.to_bytes(2, "big")).digest()
        for start in range(0, len(block), 2):
            raw = int.from_bytes(block[start : start + 2], "big")
            values.append((raw / 65535.0) * 2.0 - 1.0)
        counter += 1
    values = values[:EMBEDDING_DIMENSIONS]
    return _normalize(values)


def _at_distance(base: list[float], distance: float, salt: str) -> list[float]:
    similarity = 1.0 - distance
    ortho = _unit_vector("ortho:" + salt)
    dot = sum(left * right for left, right in zip(base, ortho))
    ortho = [value - dot * base_value for value, base_value in zip(ortho, base)]
    ortho = _normalize(ortho)
    scale = math.sqrt(max(0.0, 1.0 - similarity * similarity))
    mixed = [similarity * base_value + scale * ortho_value for base_value, ortho_value in zip(base, ortho)]
    return _normalize(mixed)


def _normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0.0:
        return values
    return [value / norm for value in values]
