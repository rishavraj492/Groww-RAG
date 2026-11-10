"""Prompt for prose answers. The model sees the question and the retrieved passages."""

from __future__ import annotations

from collections.abc import Sequence

from app.services.retrieve import Passage

SYSTEM_PROMPT = """Write two to four sentences using only the supplied passages.
If the passages do not contain the fact, set grounded to false and leave answer empty.
Do not add a number, date, or name that is not in the passages.
Do not recommend a scheme or describe expected performance.
Cite source_url values from the passages only.
Respond with JSON only, matching this schema:
{"grounded": true, "answer": "string", "citation_urls": ["string"]}
"""


def build_prompt(question: str, passages: Sequence[Passage]) -> tuple[str, str]:
    """Return the system prompt and the user message for one prose question."""
    blocks = [_passage_block(index, passage) for index, passage in enumerate(passages, start=1)]
    user = f"Question: {question.strip()}\n\n" + "\n\n".join(blocks)
    return SYSTEM_PROMPT, user


def _passage_block(index: int, passage: Passage) -> str:
    return "\n".join(
        (
            f"Passage {index}",
            f"source_url: {passage.source_url}",
            f"accessed_at: {passage.accessed_at}",
            f"authority: {passage.authority}",
            f"text: {passage.text}",
        )
    )
