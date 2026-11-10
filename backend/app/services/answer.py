"""Sentence templates for structured scheme facts. No model and no retrieval."""

import re
from dataclasses import dataclass

from app.config import EDUCATION_URLS, HOLDINGS_CAP
from app.services.facts import get_scheme
from app.services.registry import SCHEME_BY_ID
from app.services.resolve import Resolution

UNAVAILABLE_TEXT = (
    "I don’t have that in the sources for this assistant. "
    "Check the scheme page on Groww or the HDFC Mutual Fund documents for this scheme."
)
ADVISORY_REFUSAL = (
    "I can only share factual information from public sources. "
    "I can’t recommend a scheme, compare which one is better, or predict returns. "
    "For investor education, see the AMFI investor page."
)
PII_REFUSAL = (
    "Please remove identity or account details from your question and ask it again. "
    "This assistant does not read PAN, Aadhaar, phone numbers, email addresses, or OTPs."
)

_FIELD_LABELS = {
    "expense_ratio": "expense ratio",
    "exit_load": "exit load",
    "minimum_sip": "minimum SIP",
    "minimum_lumpsum": "minimum lump sum",
    "minimum_additional": "minimum additional investment",
    "riskometer": "riskometer",
    "benchmark": "benchmark",
    "category": "category",
    "nav": "NAV",
    "aum": "fund size",
    "fund_manager": "fund manager",
    "stamp_duty": "stamp duty",
    "tax_note": "tax note",
}
_VALUE_KEYS = {"nav": "nav_value"}
_EDUCATION_META = {
    "https://www.amfiindia.com/investor": ("AMFI investor education", "official"),
    "https://investor.sebi.gov.in/": ("SEBI investor education", "official"),
    "https://groww.in/learn/mutual-funds": ("Groww mutual fund education", "platform"),
}
_PROSE_KINDS = {"unknown", "definition", "elss_lock_in", "statement_download", "prose"}


@dataclass(frozen=True)
class Citation:
    url: str
    title: str
    authority: str
    accessed_at: str | None = None
    as_of: str | None = None


@dataclass(frozen=True)
class StructuredAnswer:
    response_type: str
    answer: str
    scheme_ids: tuple[str, ...]
    citations: tuple[Citation, ...]


def render_refusal(query_type: str) -> StructuredAnswer:
    """Fixed refusal for personal data or advice. Does not read scheme facts."""
    if query_type == "pii":
        text = PII_REFUSAL
    elif query_type == "advisory":
        text = ADVISORY_REFUSAL
    else:
        raise ValueError(f"not a refusal query type: {query_type}")
    return StructuredAnswer(
        response_type="refusal",
        answer=text,
        scheme_ids=(),
        citations=_education_citations(),
    )


def render(facts: list[dict], resolution: Resolution) -> StructuredAnswer:
    """Fill a template from captured fields, or say the fact is unavailable."""
    if resolution.ambiguous or resolution.kind in _PROSE_KINDS:
        scheme_ids = resolution.scheme_ids if resolution.kind == "prose" else ()
        return _unavailable(scheme_ids, facts)
    if resolution.kind == "scheme_lock_in":
        return _render_lock_in(facts, resolution.scheme_ids)
    if resolution.kind == "holdings":
        return _render_holdings(facts, resolution.scheme_ids)
    if resolution.kind == "field" and resolution.field:
        return _render_field(facts, resolution.scheme_ids, resolution.field)
    return _unavailable(resolution.scheme_ids, facts)


def _render_field(facts: list[dict], scheme_ids: tuple[str, ...], field: str) -> StructuredAnswer:
    if not scheme_ids or len(scheme_ids) > 2:
        return _unavailable((), facts)

    blocks: list[tuple[str, str | None]] = []
    citations: list[Citation] = []
    any_present = False
    for scheme_id in scheme_ids:
        record = get_scheme(facts, scheme_id)
        value = _field_value(record, field) if record is not None else None
        if record is not None and value is not None:
            any_present = True
            blocks.append((_fact_sentence(record, field, value), _accessed(record)))
            citations.append(_value_citation(record, field))
            continue
        name = _name(record) if record is not None and record.get("name") else _registry_name(scheme_id)
        blocks.append((_missing_sentence(field, name), _accessed(record) if record else None))
        citation = _groww_citation(scheme_id, record)
        if citation is not None:
            citations.append(citation)

    if not any_present:
        return _unavailable(scheme_ids, facts)
    return StructuredAnswer("factual", _compose(blocks), tuple(scheme_ids), tuple(citations))


def _render_lock_in(facts: list[dict], scheme_ids: tuple[str, ...]) -> StructuredAnswer:
    """State the scheme category and exit load. Do not apply a three-year rule."""
    if not scheme_ids or len(scheme_ids) > 2:
        return _unavailable((), facts)

    blocks: list[tuple[str, str | None]] = []
    citations: list[Citation] = []
    any_present = False
    for scheme_id in scheme_ids:
        record = get_scheme(facts, scheme_id)
        sentence = _lock_in_sentence(record) if record is not None else None
        if sentence is None:
            citation = _groww_citation(scheme_id, record)
            if citation is not None:
                citations.append(citation)
            continue
        any_present = True
        blocks.append((sentence, _accessed(record)))
        citations.append(_value_citation(record, "exit_load"))
    if not any_present:
        return _unavailable(scheme_ids, facts)
    return StructuredAnswer("factual", _compose(blocks), tuple(scheme_ids), tuple(citations))


def _render_holdings(facts: list[dict], scheme_ids: tuple[str, ...]) -> StructuredAnswer:
    if not scheme_ids or len(scheme_ids) > 2:
        return _unavailable((), facts)

    blocks: list[tuple[str, str | None]] = []
    citations: list[Citation] = []
    any_present = False
    for scheme_id in scheme_ids:
        record = get_scheme(facts, scheme_id)
        rows = _holding_rows(record)
        if record is None or not rows:
            citation = _groww_citation(scheme_id, record)
            if citation is not None:
                citations.append(citation)
            continue
        any_present = True
        shown = rows[:HOLDINGS_CAP]
        sentence = f"The holdings of {_name(record)} are {_format_holdings(shown)}."
        blocks.append((sentence, _accessed(record)))
        citations.append(_value_citation(record, "holdings"))
    if not any_present:
        return _unavailable(scheme_ids, facts)
    return StructuredAnswer("factual", _compose(blocks), tuple(scheme_ids), tuple(citations))


def _unavailable(scheme_ids: tuple[str, ...], facts: list[dict]) -> StructuredAnswer:
    citations: list[Citation] = []
    for scheme_id in scheme_ids:
        citation = _groww_citation(scheme_id, get_scheme(facts, scheme_id))
        if citation is not None:
            citations.append(citation)
    return StructuredAnswer("unavailable", UNAVAILABLE_TEXT, tuple(scheme_ids), tuple(citations))


def _education_citations() -> tuple[Citation, ...]:
    citations: list[Citation] = []
    for url in EDUCATION_URLS:
        title, authority = _EDUCATION_META[url]
        citations.append(Citation(url=url, title=title, authority=authority))
    return tuple(citations)


def _compose(blocks: list[tuple[str, str | None]]) -> str:
    prepared = [(_ensure_period(text), accessed) for text, accessed in blocks]
    dates = {accessed for _, accessed in prepared if accessed}
    if len(dates) <= 1:
        body = " ".join(text for text, _ in prepared)
        accessed = next(iter(dates), None)
        if accessed:
            return f"{body} Last updated from sources: {accessed}."
        return body
    pieces: list[str] = []
    for text, accessed in prepared:
        if accessed:
            pieces.append(f"{text} Last updated from sources: {accessed}.")
        else:
            pieces.append(text)
    return " ".join(pieces)


def _fact_sentence(record: dict, field: str, value: str) -> str:
    name = _name(record)
    if field == "nav":
        nav_date = _clean(record.get("nav_date"))
        if nav_date:
            return f"The NAV of {name} is {value} as of {nav_date}."
        return f"The NAV of {name} is {value}."
    if field == "fund_manager" and re.search(r"\b(is|are)\b", value, re.IGNORECASE):
        return _ensure_period(value)
    if field == "tax_note":
        sentence = _ensure_period(value)
        if "general description" not in value.lower():
            return f"{sentence} This is the page's general description."
        return sentence
    label = _FIELD_LABELS.get(field, field.replace("_", " "))
    return f"The {label} of {name} is {value.rstrip('.')}."


def _lock_in_sentence(record: dict) -> str | None:
    name = _name(record)
    parts: list[str] = []
    category = _clean(record.get("category"))
    exit_load = _clean(record.get("exit_load"))
    if category:
        parts.append(f"{name} is in the {category} category.")
    if exit_load:
        parts.append(f"The exit load of {name} is {exit_load.rstrip('.')}.")
    if not parts:
        return None
    return " ".join(parts)


def _missing_sentence(field: str, name: str) -> str:
    label = _FIELD_LABELS.get(field, field.replace("_", " "))
    return f"The {label} of {name} is not in the sources for this assistant."


def _field_value(record: dict, field: str) -> str | None:
    return _clean(record.get(_VALUE_KEYS.get(field, field)))


def _value_citation(record: dict, field: str) -> Citation:
    scheme = SCHEME_BY_ID.get(str(record.get("scheme_id") or ""))
    authority = _clean(record.get("authority")) or "platform"
    source = _clean(record.get("source_url"))
    if authority == "official" and source:
        url = source
    elif scheme is not None:
        url = scheme.url
    else:
        url = source or ""
    as_of = _clean(record.get("as_of"))
    if field == "nav" and not as_of:
        as_of = _clean(record.get("nav_date"))
    return Citation(
        url=url,
        title=_name(record),
        authority=authority,
        accessed_at=_accessed(record),
        as_of=as_of,
    )


def _groww_citation(scheme_id: str, record: dict | None) -> Citation | None:
    scheme = SCHEME_BY_ID.get(scheme_id)
    if scheme is None:
        return None
    title = _name(record) if record is not None and record.get("name") else scheme.name
    return Citation(
        url=scheme.url,
        title=title,
        authority="platform",
        accessed_at=_accessed(record) if record else None,
    )


def _holding_rows(record: dict | None) -> list[dict]:
    if record is None:
        return []
    rows = record.get("holdings")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and _clean(row.get("name"))]


def _format_holdings(rows: list[dict]) -> str:
    parts: list[str] = []
    for row in rows:
        name = _clean(row.get("name")) or ""
        sector = _clean(row.get("sector"))
        weight = _clean(row.get("weight"))
        detail = ", ".join(item for item in (sector, weight) if item)
        parts.append(f"{name} ({detail})" if detail else name)
    return "; ".join(parts)


def _name(record: dict) -> str:
    named = _clean(record.get("name"))
    if named:
        return named
    scheme = SCHEME_BY_ID.get(str(record.get("scheme_id") or ""))
    if scheme is not None:
        return scheme.name
    return str(record.get("scheme_id") or "this scheme")


def _registry_name(scheme_id: str) -> str:
    scheme = SCHEME_BY_ID.get(scheme_id)
    if scheme is not None:
        return scheme.name
    return scheme_id


def _accessed(record: dict | None) -> str | None:
    if record is None:
        return None
    return _clean(record.get("accessed_at"))


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _ensure_period(text: str) -> str:
    text = text.strip()
    if text.endswith((".", "!", "?")):
        return text
    return text + "."
