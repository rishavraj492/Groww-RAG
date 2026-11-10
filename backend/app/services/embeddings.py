"""Local passage embeddings. Questions get a retrieval prefix; passages do not."""

from __future__ import annotations

from typing import Protocol

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
EMBEDDING_DIMENSIONS = 384


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one unit vector per text. The caller applies the query prefix."""


class LocalEmbedder:
    """BAAI/bge-small-en-v1.5, 384 dimensions, vectors normalized for cosine distance."""

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self._model = SentenceTransformer(model_name, device="cpu")

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(
            list(texts),
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [[float(value) for value in row] for row in vectors]


def build_embedder(model_name: str) -> LocalEmbedder:
    """Load the configured local model. Tests pass a fake embedder instead."""
    return LocalEmbedder(model_name)
