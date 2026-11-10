from pydantic import BaseModel, ConfigDict, Field


class SchemeRef(BaseModel):
    id: str
    name: str


class CitationModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    url: str
    title: str
    authority: str
    accessed_at: str | None = Field(default=None, alias="accessedAt")
    as_of: str | None = Field(default=None, alias="asOf")


class QueryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    response_type: str = Field(alias="responseType")
    query_type: str = Field(alias="queryType")
    answer: str
    scheme: SchemeRef | None = None
    citations: list[CitationModel]


class SchemeSummary(BaseModel):
    """Suggestion-chip fields. Scheme values are not included."""

    scheme_id: str
    name: str
    url: str
