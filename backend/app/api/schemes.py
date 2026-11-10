from fastapi import APIRouter

from app.schemas.response import SchemeSummary
from app.services.registry import SCHEMES

router = APIRouter()


@router.get("/schemes", response_model=list[SchemeSummary])
def schemes() -> list[SchemeSummary]:
    return [
        SchemeSummary(scheme_id=scheme.scheme_id, name=scheme.name, url=scheme.url)
        for scheme in SCHEMES
    ]
