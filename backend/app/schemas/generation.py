"""JSON object the prose model must return."""

from pydantic import BaseModel, ConfigDict


class GenerationDraft(BaseModel):
    """Grounded answer and the passage URLs it claims to use."""

    model_config = ConfigDict(extra="ignore")

    grounded: bool
    answer: str
    citation_urls: list[str]


GENERATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["grounded", "answer", "citation_urls"],
    "properties": {
        "grounded": {"type": "boolean"},
        "answer": {"type": "string"},
        "citation_urls": {"type": "array", "items": {"type": "string"}},
    },
}
