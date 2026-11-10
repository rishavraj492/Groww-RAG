from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.query import router as query_router
from app.api.schemes import router as schemes_router
from app.config import (
    CHROMA_PATH,
    CORS_ORIGINS,
    EMBEDDING_MODEL,
    FACTS_PATH,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
)
from app.services.facts import oldest_accessed_at, require_facts
from app.services.index import open_collection, require_loaded_index
from app.services.llm_client import LLMClient


def create_app(
    facts_path: Path | None = None,
    chroma_path: Path | None = None,
    manifest_path: Path | None = None,
) -> FastAPI:
    path = FACTS_PATH if facts_path is None else facts_path
    index_path = CHROMA_PATH if chroma_path is None else chroma_path
    manifest = path.with_name("manifest.json") if manifest_path is None else manifest_path

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        facts = require_facts(path)
        app.state.passage_count = require_loaded_index(manifest, index_path, EMBEDDING_MODEL)
        app.state.facts = facts
        app.state.oldest_accessed_at = oldest_accessed_at(facts)
        app.state.collection = open_collection(index_path) if index_path.exists() else None
        app.state.embedder = None

        def embedder_factory():
            if app.state.embedder is None:
                from app.services.embeddings import build_embedder

                app.state.embedder = build_embedder(EMBEDDING_MODEL)
            return app.state.embedder

        app.state.embedder_factory = embedder_factory
        llm_client = LLMClient(
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL,
            model=LLM_MODEL,
            timeout_seconds=LLM_TIMEOUT_SECONDS,
        )
        app.state.llm_client = llm_client
        try:
            yield
        finally:
            llm_client.close()

    app = FastAPI(title="Facts-Only Mutual Fund FAQ Assistant", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(CORS_ORIGINS),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix="/api")
    app.include_router(schemes_router, prefix="/api")
    app.include_router(query_router, prefix="/api")
    return app


app = create_app()
