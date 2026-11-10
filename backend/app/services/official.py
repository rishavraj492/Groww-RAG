"""Official-document field extraction, value normalization, and Groww merge rules."""

from __future__ import annotations

import io
import re
from typing import Any

from bs4 import BeautifulSoup

MERGEABLE_FIELDS = (
    "category",
    "riskometer",
    "expense_ratio",
    "exit_load",
    "minimum_sip",
    "minimum_lumpsum",
    "minimum_additional",
    "nav_value",
    "nav_date",
    "aum",
    "benchmark",
    "fund_manager",
    "stamp_duty",
    "tax_note",
)

_SCHEME_DOC_TYPES = frozenset({"factsheet", "sid"})

_LABEL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("expense ratio", "expense_ratio"),
    ("total expense ratio", "expense_ratio"),
    ("exit load", "exit_load"),
    ("minimum sip", "minimum_sip"),
    ("min. for sip", "minimum_sip"),
    ("min sip", "minimum_sip"),
    ("minimum lump sum", "minimum_lumpsum"),
    ("min. for 1st investment", "minimum_lumpsum"),
    ("riskometer", "riskometer"),
    ("risk-o-meter", "riskometer"),
    ("fund benchmark", "benchmark"),
    ("benchmark", "benchmark"),
    ("fund size", "aum"),
    ("aum", "aum"),
    ("category", "category"),
    ("stamp duty", "stamp_duty"),
)

_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_RUPEE = re.compile(r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)", re.I)
_PLAIN_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_WHITESPACE = re.compile(r"\s+")


def is_scheme_official_doc(document_type: str | None) -> bool:
    return (document_type or "") in _SCHEME_DOC_TYPES


def normalize_fact_value(field: str, value: str | None) -> str | None:
    """Compare Groww and official values without averaging or inventing a form."""
    if value is None:
        return None
    text = _WHITESPACE.sub(" ", str(value).replace("\xa0", " ")).strip()
    if not text:
        return None
    if field == "expense_ratio":
        match = _PERCENT.search(text) or _PLAIN_NUMBER.fullmatch(text)
        if not match:
            return text.casefold()
        number = float(match.group(1) if match.lastindex else match.group(0))
        return f"{number:.4f}"
    if field in {"minimum_sip", "minimum_lumpsum", "minimum_additional", "nav_value", "aum"}:
        match = _RUPEE.search(text)
        if match:
            number = float(match.group(1).replace(",", ""))
            return f"{number:.4f}"
        plain = _PLAIN_NUMBER.fullmatch(text.replace(",", ""))
        if plain:
            return f"{float(plain.group(0)):.4f}"
        return text.casefold()
    if field == "riskometer":
        return re.sub(r"\s+risk$", "", text, flags=re.I).casefold().strip()
    if field == "nav_date":
        return text
    return text.casefold()


def values_match(field: str, left: str | None, right: str | None) -> bool:
    a = normalize_fact_value(field, left)
    b = normalize_fact_value(field, right)
    if a is None or b is None:
        return False
    return a == b


def merge_official_fields(
    platform: dict[str, Any],
    official_fields: dict[str, Any],
    *,
    official_url: str,
    authority: str = "official",
) -> tuple[dict[str, Any], dict[str, str]]:
    """Prefer official values for overlapping fields. Return conflicts as platform_value map.

    Matching and conflicting fields both store the official value and point the record
    at the official URL. Differing Groww values are returned for the manifest only.
    """
    merged = dict(platform)
    platform_value: dict[str, str] = {}
    touched = False
    for field in MERGEABLE_FIELDS:
        official = _clean(official_fields.get(field))
        if official is None:
            continue
        current = _clean(merged.get(field))
        if current is not None and not values_match(field, current, official):
            platform_value[field] = current
        merged[field] = official
        touched = True
    if touched:
        merged["source_url"] = official_url
        merged["authority"] = authority or "official"
    return merged, platform_value


def extract_fields_from_html(html: str) -> dict[str, str]:
    """Read labeled scheme fields from an AMC HTML factsheet or SID page."""
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, str] = {}
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        field = _match_html_label(cells[0].get_text(" ", strip=True))
        if field is None or field in found:
            continue
        value = _clean(cells[1].get_text(" ", strip=True))
        if value:
            found[field] = _format_html_value(field, value)
    for term in soup.find_all("dt"):
        field = _match_html_label(term.get_text(" ", strip=True))
        definition = term.find_next_sibling("dd")
        if field is None or field in found or definition is None:
            continue
        value = _clean(definition.get_text(" ", strip=True))
        if value:
            found[field] = _format_html_value(field, value)
    for label in soup.find_all(class_="label"):
        field = _match_html_label(label.get_text(" ", strip=True))
        if field is None or field in found:
            continue
        value_node = label.find_next_sibling(class_="value")
        if value_node is None:
            sibling = label.next_sibling
            while sibling is not None and not getattr(sibling, "name", None):
                sibling = sibling.next_sibling
            value_node = sibling
        if value_node is None:
            continue
        value = _clean(value_node.get_text(" ", strip=True))
        if value:
            found[field] = _format_html_value(field, value)
    return found


def _match_html_label(text: str) -> str | None:
    normalized = _WHITESPACE.sub(" ", text.replace("\xa0", " ")).casefold().rstrip(":").strip()
    for label, field in _LABEL_PATTERNS:
        if normalized == label:
            return field
    return None


def _format_html_value(field: str, value: str) -> str:
    if field == "expense_ratio":
        match = _PERCENT.search(value) or _PLAIN_NUMBER.fullmatch(value.strip())
        if match:
            number = float(match.group(1) if match.lastindex else match.group(0))
            return f"{number:.2f}%"
    if field in {"minimum_sip", "minimum_lumpsum", "minimum_additional", "nav_value", "aum"}:
        match = _RUPEE.search(value)
        if match:
            number = float(match.group(1).replace(",", ""))
            if field == "aum":
                suffix = " Cr" if re.search(r"\bcr\b", value, re.I) else ""
                if number.is_integer():
                    return f"₹{int(number):,}{suffix}"
                return f"₹{number:,.2f}{suffix}"
            if number.is_integer():
                return f"₹{int(number):,}"
            return f"₹{number:,.2f}"
    if field == "riskometer":
        return re.sub(r"\s+risk$", "", value, flags=re.I).strip()
    return value


def extract_fields_from_text(text: str) -> dict[str, str]:
    """Pull labeled fields from PDF or plain-text official documents."""
    found: dict[str, str] = {}
    collapsed = _WHITESPACE.sub(" ", text.replace("\xa0", " "))
    lower = collapsed.casefold()
    for label, field in _LABEL_PATTERNS:
        if field in found:
            continue
        index = lower.find(label)
        if index < 0:
            continue
        after = collapsed[index + len(label) : index + len(label) + 160]
        after = after.lstrip(" \t:-–—|")
        value = _value_after_label(field, after)
        if value:
            found[field] = value
    return found


def extract_pdf_text(data: bytes) -> str | None:
    """Return extracted text, or None when the PDF has no text layer."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception:
        return None
    parts: list[str] = []
    for page in reader.pages:
        try:
            piece = page.extract_text() or ""
        except Exception:
            continue
        piece = piece.strip()
        if piece:
            parts.append(piece)
    if not parts:
        return None
    return "\n".join(parts)


def extract_official_fields(body: str | bytes) -> dict[str, str]:
    """HTML when it looks like markup; otherwise PDF bytes or plain text."""
    if isinstance(body, bytes):
        if body.lstrip().startswith(b"%PDF"):
            text = extract_pdf_text(body)
            if text is None:
                return {}
            return extract_fields_from_text(text)
        body = body.decode("utf-8", errors="replace")
    stripped = body.lstrip()
    if stripped.startswith("%PDF"):
        text = extract_pdf_text(body.encode("utf-8", errors="replace"))
        if text is None:
            return {}
        return extract_fields_from_text(text)
    if "<html" in stripped[:500].casefold() or "<!doctype" in stripped[:500].casefold() or "<div" in stripped[:1000].casefold():
        return extract_fields_from_html(body)
    return extract_fields_from_text(body)


def _value_after_label(field: str, after: str) -> str | None:
    if field == "expense_ratio":
        match = _PERCENT.search(after)
        if match:
            return f"{float(match.group(1)):.2f}%"
        return None
    if field in {"minimum_sip", "minimum_lumpsum", "minimum_additional", "nav_value"}:
        match = _RUPEE.search(after)
        if match:
            number = float(match.group(1).replace(",", ""))
            if number.is_integer():
                return f"₹{int(number):,}"
            return f"₹{number:,.2f}"
        return None
    if field == "aum":
        match = _RUPEE.search(after)
        if match:
            number = float(match.group(1).replace(",", ""))
            rest = after[match.end() : match.end() + 12]
            suffix = " Cr" if re.match(r"\s*cr\b", rest, re.I) else ""
            return f"₹{number:,.2f}{suffix}".replace(".00", "") if number.is_integer() else f"₹{number:,.2f}{suffix}"
        return None
    if field == "riskometer":
        match = re.match(
            r"(Very High|Moderately High|Low to Moderate|Moderate|Low)(?:\s+Risk)?",
            after,
            re.I,
        )
        if match:
            return match.group(1)
        return None
    if field == "exit_load":
        sentence = after.split(".")[0].strip()
        return sentence or None
    if field in {"benchmark", "category", "stamp_duty"}:
        sentence = re.split(r"[\n|]", after, maxsplit=1)[0].strip()
        sentence = sentence.split(".")[0].strip()
        return sentence or None
    return None


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = _WHITESPACE.sub(" ", str(value).replace("\xa0", " ")).strip()
    return text or None
