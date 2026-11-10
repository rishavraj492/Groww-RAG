from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import QUESTION_MAX_LENGTH
from app.services.registry import SCHEME_BY_ID


class QueryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    question: str
    prior_scheme_id: str | None = Field(default=None, alias="priorSchemeId")

    @field_validator("question")
    @classmethod
    def question_within_cap(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("question must not be empty")
        if len(text) > QUESTION_MAX_LENGTH:
            raise ValueError(f"question must be at most {QUESTION_MAX_LENGTH} characters")
        return text

    @field_validator("prior_scheme_id")
    @classmethod
    def prior_scheme_is_known(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in SCHEME_BY_ID:
            raise ValueError("unknown priorSchemeId")
        return value
