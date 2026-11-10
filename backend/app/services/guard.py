"""Keep a prose draft only when its citations and numbers are in the retrieved passages."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from app.config import ANSWER_MAX_CHARS, ANSWER_MAX_SENTENCES
from app.schemas.generation import GenerationDraft
from app.services.answer import Citation
from app.services.retrieve import Passage

_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_RUPEE = re.compile(r"(?:₹|Rs\.?|INR)\s?\d[\d,]*(?:\.\d+)?", re.IGNORECASE)
_PERCENT = re.compile(r"\d[\d,]*(?:\.\d+)?\s?%")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


@dataclass(frozen=True)
class GroundedAnswer:
    answer: str
    citations: tuple[Citation, ...]


def guard(raw: str, passages: Sequence[Passage]) -> GroundedAnswer | None:
    """Return the capped answer and surviving citations, or None when the draft is unusable.

    A failed check does not return the passage text. The caller uses the unavailable template.
    """
    draft = _parse(raw)
    if draft is None or not draft.grounded or not draft.answer.strip():
        return None
    passage_text = "\n".join(passage.text for passage in passages)
    if not _numbers_supported(draft.answer, passage_text):
        return None
    urls = _surviving_urls(draft.citation_urls, passages)
    if not urls:
        return None
    answer = _cap_answer(draft.answer)
    if not answer or not _numbers_supported(answer, passage_text):
        return None
    return GroundedAnswer(answer=answer, citations=tuple(_citations(urls, passages)))


def _parse(raw: str) -> GenerationDraft | None:
    if not isinstance(raw, str):
        return None
    try:
        return GenerationDraft.model_validate_json(raw)
    except ValidationError:
        return None


def _numbers_supported(answer: str, passage_text: str) -> bool:
    compact_passage = re.sub(r"\s+", "", passage_text)
    for token in _number_tokens(answer):
        compact = re.sub(r"\s+", "", token)
        if not compact:
            continue
        pattern = re.escape(compact) + r"(?!\d)"
        if re.search(pattern, compact_passage) is None:
            return False
    return True


def _number_tokens(text: str) -> list[str]:
    occupied: list[tuple[int, int]] = []
    found: list[tuple[int, str]] = []

    def take(pattern: re.Pattern[str]) -> None:
        for match in pattern.finditer(text):
            span = match.span()
            if any(start < span[1] and span[0] < end for start, end in occupied):
                continue
            occupied.append(span)
            found.append((span[0], match.group()))

    take(_RUPEE)
    take(_PERCENT)
    take(_NUMBER)
    found.sort(key=lambda item: item[0])
    return [token for _, token in found]


def _surviving_urls(urls: Sequence[str], passages: Sequence[Passage]) -> list[str]:
    known = {passage.source_url for passage in passages}
    seen: list[str] = []
    for url in urls:
        cleaned = url.strip()
        if cleaned in known and cleaned not in seen:
            seen.append(cleaned)

    def rank(item: tuple[int, str]) -> tuple[int, int]:
        index, url = item
        passage = _passage_for(url, passages)
        official = 0 if passage is not None and passage.authority == "official" else 1
        return (official, index)

    return [url for _, url in sorted(enumerate(seen), key=rank)]


def _citations(urls: Sequence[str], passages: Sequence[Passage]) -> list[Citation]:
    citations: list[Citation] = []
    for url in urls:
        passage = _passage_for(url, passages)
        if passage is None:
            continue
        citations.append(
            Citation(
                url=passage.source_url,
                title=passage.title or passage.source_url,
                authority=passage.authority or "platform",
                accessed_at=passage.accessed_at or None,
                as_of=passage.as_of,
            )
        )
    return citations


def _passage_for(url: str, passages: Sequence[Passage]) -> Passage | None:
    matches = [passage for passage in passages if passage.source_url == url]
    if not matches:
        return None
    matches.sort(key=lambda passage: 0 if passage.authority == "official" else 1)
    return matches[0]


def _cap_answer(text: str) -> str:
    sentences = [part.strip() for part in _SENTENCE_BREAK.split(text.strip()) if part.strip()]
    if not sentences:
        return ""
    joined = " ".join(sentences[:ANSWER_MAX_SENTENCES]).strip()
    if len(joined) <= ANSWER_MAX_CHARS:
        return joined
    clipped = joined[:ANSWER_MAX_CHARS]
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.rstrip()
