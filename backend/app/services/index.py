"""Persistent Chroma collection for scheme-page passages."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import chromadb
from chromadb.config import Settings
from chromadb.errors import NotFoundError

from app.services.embeddings import Embedder

logger = logging.getLogger(__name__)

COLLECTION_NAME = "scheme_passages"

_METADATA_FIELDS = (
    "source_url",
    "title",
    "authority",
    "document_type",
    "scheme_id",
    "topic",
    "accessed_at",
    "as_of",
)


def open_collection(chroma_path: Path):
    """Open `scheme_passages` with cosine distance. Creates the directory when indexing."""
    chroma_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(
        path=str(chroma_path),
        settings=Settings(anonymized_telemetry=False),
    )
    try:
        collection = client.get_collection(name=COLLECTION_NAME)
    except NotFoundError:
        collection = None
    space = (collection.metadata or {}).get("hnsw:space") if collection is not None else None
    if collection is not None and space != "cosine":
        client.delete_collection(COLLECTION_NAME)
        collection = None
    if collection is None:
        collection = client.create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return collection


def index_passages(chroma_path: Path, passages: list[dict], embedder: Embedder):
    """Replace each source URL's rows with the passages from this ingest."""
    collection = open_collection(chroma_path)
    grouped: dict[str, list[dict]] = {}
    for passage in passages:
        url = passage.get("source_url")
        if isinstance(url, str) and url:
            grouped.setdefault(url, []).append(passage)

    vectors: list[list[float]] = []
    if passages:
        vectors = embedder.embed([str(passage["text"]) for passage in passages])
        if len(vectors) != len(passages):
            raise ValueError("embedder returned a different number of vectors than passages")

    existing = collection.get(include=["metadatas"])
    stale: list[str] = []
    for item_id, metadata in zip(existing.get("ids") or [], existing.get("metadatas") or []):
        url = (metadata or {}).get("source_url")
        if url not in grouped:
            stale.append(item_id)
    if stale:
        collection.delete(ids=stale)

    if not passages:
        return collection

    by_url_vectors: dict[str, list[tuple[dict, list[float]]]] = {}
    for passage, vector in zip(passages, vectors):
        url = passage.get("source_url")
        if isinstance(url, str) and url:
            by_url_vectors.setdefault(url, []).append((passage, vector))

    for url, rows in by_url_vectors.items():
        _replace_url(collection, url, rows)
    return collection


def passage_count(chroma_path: Path) -> int:
    """How many passages are stored. A missing directory counts as empty and is not created."""
    if not chroma_path.exists():
        return 0
    return int(open_collection(chroma_path).count())


def require_loaded_index(manifest_path: Path, chroma_path: Path, embedding_model: str) -> int:
    """Refuse to serve when the manifest names a different model, or claims passages that are missing."""
    manifest = _read_manifest(manifest_path)
    claimed = 0
    if manifest is not None:
        recorded = manifest.get("embedding_model")
        if isinstance(recorded, str) and recorded and recorded != embedding_model:
            logger.error(
                "Manifest embedding model %s does not match %s. Run python scripts/ingest.py",
                recorded,
                embedding_model,
            )
            raise SystemExit(1)
        raw_count = manifest.get("passage_count")
        if isinstance(raw_count, int):
            claimed = raw_count
    count = passage_count(chroma_path)
    if claimed > 0 and count == 0:
        logger.error(
            "Passage index at %s is empty. Run python scripts/ingest.py",
            chroma_path,
        )
        raise SystemExit(1)
    return count


def _replace_url(collection, url: str, rows: list[tuple[dict, list[float]]]) -> None:
    collection.delete(where={"source_url": url})
    collection.add(
        ids=[_passage_id(passage, index) for index, (passage, _vector) in enumerate(rows)],
        embeddings=[vector for _passage, vector in rows],
        documents=[str(passage["text"]) for passage, _vector in rows],
        metadatas=[_metadata(passage) for passage, _vector in rows],
    )


def _passage_id(passage: dict, index: int) -> str:
    raw = f"{passage.get('source_url')}\n{index}\n{passage.get('topic')}\n{passage.get('text')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _metadata(passage: dict) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for field in _METADATA_FIELDS:
        value = passage.get(field)
        metadata[field] = "" if value is None else str(value)
    return metadata


def _read_manifest(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Could not read manifest at %s. Run python scripts/ingest.py", path)
        raise SystemExit(1) from exc
    if not isinstance(payload, dict):
        logger.error("Manifest at %s is not an object. Run python scripts/ingest.py", path)
        raise SystemExit(1)
    return payload
