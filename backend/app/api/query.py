from fastapi import APIRouter, Request

from app.schemas.request import QueryRequest
from app.schemas.response import QueryResponse
from app.services.query_service import answer_query

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
def query(body: QueryRequest, request: Request) -> QueryResponse:
    state = request.app.state
    return answer_query(
        body.question,
        body.prior_scheme_id,
        state.facts,
        collection=getattr(state, "collection", None),
        embedder=getattr(state, "embedder", None),
        embedder_factory=getattr(state, "embedder_factory", None),
        llm_client=getattr(state, "llm_client", None),
    )
