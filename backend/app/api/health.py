from fastapi import APIRouter, Request

from app.config import EMBEDDING_MODEL

router = APIRouter()


@router.get("/health")
def health(request: Request) -> dict:
    facts = getattr(request.app.state, "facts", None)
    loaded = isinstance(facts, list)
    return {
        "status": "ok",
        "factsLoaded": loaded,
        "schemeCount": len(facts) if loaded else 0,
        "passageCount": getattr(request.app.state, "passage_count", 0) if loaded else 0,
        "embeddingModel": EMBEDDING_MODEL,
        "oldestAccessedAt": getattr(request.app.state, "oldest_accessed_at", None) if loaded else None,
    }
