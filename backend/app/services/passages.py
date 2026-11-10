"""Split scheme pages into one passage per prose field.

Live Groww pages are read from ``mfServerSideData``. Fixture HTML has no
embedded JSON, so those pages are read from headings and the stamp-duty and
tax labels. Labeled numbers, holdings, returns, and the About paragraph are
not passages. Nothing here embeds text or reads a PDF.
"""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from app.services.registry import SCHEME_BY_ID

TOKEN_SPLIT_AT = 400
TOKEN_HARD_LIMIT = 512
TOKEN_OVERLAP = 50

PASSAGE_FIELDS = (
    "text",
    "source_url",
    "title",
    "authority",
    "document_type",
    "scheme_id",
    "topic",
    "accessed_at",
    "as_of",
)

_EXCLUDED_HEADING = re.compile(
    r"^(about|returns|trailing returns|annualised returns|annualized returns|"
    r"returns and rankings|rank|ranking|rankings|rank table|calculator|"
    r"return calculator|holdings|compare similar funds|peer comparison|"
    r"understand terms|exit load|fund house|fund management)\b",
    re.I,
)

_OBJECTIVE_HEADING = re.compile(r"^investment objective\b", re.I)
_MANAGER_HEADING = re.compile(r"^fund managers?\b", re.I)


def estimate_tokens(text: str) -> int:
    """WordPiece-sized estimate: about 1.3 tokens per whitespace word."""
    words = text.split()
    if not words:
        return 0
    return max(1, round(len(words) * 1.3))


def chunk_scheme_html(
    html: str,
    *,
    scheme_id: str,
    source_url: str,
    title: str,
    authority: str,
    document_type: str,
    accessed_at: str,
    as_of: str | None,
) -> list[dict]:
    """Return passages for one scheme page. An unknown scheme or a PDF body yields none."""
    if scheme_id not in SCHEME_BY_ID or document_type != "scheme_page":
        return []
    if html.lstrip().startswith("%PDF"):
        return []
    data = _server_data(html)
    if data is not None:
        drafts = _passages_from_server_data(data)
    else:
        drafts = _passages_from_headings(html)
    passages: list[dict] = []
    for topic, heading, body in drafts:
        text = _prefixed(heading, body)
        if not text:
            continue
        for piece in split_passage(text):
            passages.append(
                _passage(
                    text=piece,
                    source_url=source_url,
                    title=title,
                    authority=authority,
                    document_type=document_type,
                    scheme_id=scheme_id,
                    topic=topic,
                    accessed_at=accessed_at,
                    as_of=as_of,
                )
            )
    return passages


def chunk_general_html(
    html: str,
    *,
    source_url: str,
    title: str,
    authority: str,
    document_type: str,
    topic: str,
    accessed_at: str,
    as_of: str | None = None,
    scheme_id: str = "",
) -> list[dict]:
    """One or more passages from a regulatory or help page. Empty scheme_id for general docs."""
    if html.lstrip().startswith("%PDF"):
        return []
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = _clean(soup.get_text(" ", strip=True)) or ""
    if not text:
        return []
    passages: list[dict] = []
    for piece in split_passage(text):
        passages.append(
            _passage(
                text=piece,
                source_url=source_url,
                title=title,
                authority=authority,
                document_type=document_type,
                scheme_id=scheme_id or "",
                topic=topic or "other",
                accessed_at=accessed_at,
                as_of=as_of,
            )
        )
    return passages


def split_passage(text: str) -> list[str]:
    """Keep one field intact. Split only past 400 tokens, with a small overlap, under 512."""
    words = text.split()
    if estimate_tokens(text) <= TOKEN_SPLIT_AT:
        return [" ".join(words)] if words else []
    window = _max_words(TOKEN_SPLIT_AT)
    overlap = min(_max_words(TOKEN_OVERLAP), max(1, window // 5))
    if overlap >= window:
        overlap = max(1, window // 5)
    pieces: list[str] = []
    start = 0
    while start < len(words):
        end = min(len(words), start + window)
        piece = " ".join(words[start:end])
        if estimate_tokens(piece) > TOKEN_HARD_LIMIT:
            end = start + max(1, window - 1)
            piece = " ".join(words[start:end])
        pieces.append(piece)
        if end >= len(words):
            break
        next_start = end - overlap
        if next_start <= start:
            next_start = start + 1
        start = next_start
    return pieces


def _passages_from_server_data(data: dict) -> list[tuple[str, str, str]]:
    drafts: list[tuple[str, str, str]] = []
    description = _clean(data.get("description"))
    if description:
        drafts.append(("objective", "Investment objective", description))
    category = data.get("category_info")
    tax = _clean(category.get("tax_impact")) if isinstance(category, dict) else None
    if tax:
        drafts.append(("tax_note", "Tax implication", tax))
    stamp = _clean(data.get("stamp_duty"))
    if stamp:
        drafts.append(("stamp_duty", "Stamp duty", stamp))
    for manager in _current_managers(data.get("fund_manager_details")):
        body = _manager_body(manager)
        if body:
            drafts.append(("fund_manager", "Fund manager", body))
    return drafts


def _passages_from_headings(html: str) -> list[tuple[str, str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    drafts: list[tuple[str, str, str]] = []
    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        title = _clean(heading.get_text(" ", strip=True)) or ""
        if not title or _EXCLUDED_HEADING.match(title):
            continue
        if _OBJECTIVE_HEADING.match(title):
            body = _heading_body(heading)
            if body:
                drafts.append(("objective", "Investment objective", body))
        elif _MANAGER_HEADING.match(title):
            body = _heading_body(heading)
            if body:
                drafts.append(("fund_manager", "Fund manager", body))
    for label, topic, heading in (
        ("stamp duty", "stamp_duty", "Stamp duty"),
        ("tax implication", "tax_note", "Tax implication"),
    ):
        value = _labeled_value(soup, label)
        if value:
            drafts.append((topic, heading, value))
    return drafts


def _server_data(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script"):
        script_type = (script.get("type") or "").casefold()
        script_id = (script.get("id") or "").casefold()
        if script_type not in {"application/json", "application/ld+json"} and script_id != "__next_data__":
            continue
        raw = script.string or script.get_text()
        if not raw or "mfServerSideData" not in raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        found = _find_server_data(payload)
        if found is not None:
            return found
    return None


def _find_server_data(node) -> dict | None:
    if isinstance(node, dict):
        data = node.get("mfServerSideData")
        if isinstance(data, dict):
            return data
        for child in node.values():
            found = _find_server_data(child)
            if found is not None:
                return found
    elif isinstance(node, list):
        for child in node:
            found = _find_server_data(child)
            if found is not None:
                return found
    return None


def _current_managers(details) -> list[dict]:
    if not isinstance(details, list):
        return []
    current: list[dict] = []
    for item in details:
        if isinstance(item, dict) and _is_current_manager(item):
            current.append(item)
    return current


def _is_current_manager(manager: dict) -> bool:
    end = (
        manager.get("date_to")
        or manager.get("dateTo")
        or manager.get("to_date")
        or manager.get("end_date")
    )
    if end is None:
        return True
    text = (_clean(str(end)) or "").casefold()
    return text in {"", "present", "- present", "till date", "current"}


def _manager_body(manager: dict) -> str | None:
    name = _clean(manager.get("person_name") or manager.get("personName") or manager.get("name"))
    education = _clean(manager.get("education"))
    experience = _clean(manager.get("experience"))
    if not name or (not education and not experience):
        return None
    return " ".join(part for part in (name, education, experience) if part)


def _heading_body(heading) -> str | None:
    section = heading.find_parent("section")
    scope = section if section is not None else heading.parent
    if scope is None:
        return None
    value = scope.select_one(".value")
    if value is not None:
        return _clean(value.get_text(" ", strip=True))
    parts: list[str] = []
    for node in heading.next_siblings:
        name = getattr(node, "name", None)
        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            break
        text = node.get_text(" ", strip=True) if name else str(node)
        cleaned = _clean(text)
        if cleaned:
            parts.append(cleaned)
    return _clean(" ".join(parts))


def _labeled_value(soup: BeautifulSoup, label: str) -> str | None:
    for node in soup.find_all(class_="label"):
        if _normalize_label(node.get_text(" ", strip=True)) != label:
            continue
        if _inside_excluded_section(node):
            continue
        value_node = node.find_next_sibling(class_="value")
        if value_node is None:
            continue
        value = _clean(value_node.get_text(" ", strip=True))
        if value:
            return value
    return None


def _inside_excluded_section(node) -> bool:
    section = node.find_parent("section")
    if section is None:
        return False
    heading = section.find(["h1", "h2", "h3", "h4", "h5", "h6"])
    if heading is None:
        return False
    title = _clean(heading.get_text(" ", strip=True)) or ""
    return bool(_EXCLUDED_HEADING.match(title))


def _prefixed(heading: str, body: str) -> str:
    body = _clean(body) or ""
    if not body:
        return ""
    if body.casefold().startswith(heading.casefold()):
        return body
    return f"{heading}: {body}"


def _passage(
    *,
    text: str,
    source_url: str,
    title: str,
    authority: str,
    document_type: str,
    scheme_id: str,
    topic: str,
    accessed_at: str,
    as_of: str | None,
) -> dict:
    return {
        "text": text,
        "source_url": source_url,
        "title": title,
        "authority": authority,
        "document_type": document_type,
        "scheme_id": scheme_id,
        "topic": topic,
        "accessed_at": accessed_at,
        "as_of": as_of,
    }


def _max_words(token_budget: int) -> int:
    best = 1
    low = 1
    high = token_budget
    while low <= high:
        mid = (low + high) // 2
        if estimate_tokens(" ".join(["word"] * mid)) <= token_budget:
            best = mid
            low = mid + 1
        else:
            high = mid - 1
    return best


def _normalize_label(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split()).casefold().rstrip(":").strip()


def _clean(value) -> str | None:
    if value is None:
        return None
    collapsed = " ".join(str(value).replace("\xa0", " ").split())
    return collapsed or None
