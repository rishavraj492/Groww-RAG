"""Map a factual question to schemes, a structured field, or a prose topic."""

import re
from dataclasses import dataclass

from app.services.registry import SCHEMES

_FIELD_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("expense_ratio", re.compile(r"\bexpense ratios?\b")),
    ("exit_load", re.compile(r"\bexit loads?\b")),
    ("minimum_lumpsum", re.compile(r"\blump sums?\b|\blumpsums?\b|\b1st investments?\b|\bfirst investments?\b")),
    ("minimum_additional", re.compile(r"\badditional investments?\b|\b2nd investments?\b|\bsecond investments?\b")),
    ("minimum_sip", re.compile(r"\bsips?\b")),
    ("riskometer", re.compile(r"\briskometers?\b|\brisk labels?\b")),
    ("benchmark", re.compile(r"\bbenchmarks?\b")),
    ("category", re.compile(r"\bcategor(?:y|ies)\b")),
    ("nav", re.compile(r"\bnav\b|\bnet asset values?\b")),
    ("aum", re.compile(r"\baum\b|\bfund sizes?\b|\bassets under management\b")),
    ("fund_manager", re.compile(r"\bfund managers?\b|\bwho manages\b|\bwho is the manager\b")),
    ("stamp_duty", re.compile(r"\bstamp duty\b")),
    ("tax_note", re.compile(r"\btax notes?\b|\btax implications?\b")),
)

_STATEMENT = re.compile(
    r"capital gains statements?|account statements?|consolidated account statements?|"
    r"\bdownload\b.{0,40}\bstatements?\b|\bstatements?\b.{0,40}\bdownload\b"
)
_ELSS = re.compile(r"\belss\b")
_LOCK_IN = re.compile(r"\block in\b|\blockin\b")
_DEFINABLE = re.compile(r"\b(?:expense ratios?|riskometers?|exit loads?)\b")
_DEFINITION = re.compile(r"\bwhat is an?\b|\bdefine\b|\bdefinition of\b|\bmeaning of\b|\bwhat does\b.+\bmean\b")
_HOLDINGS = re.compile(r"\bholdings\b")
_OBJECTIVE = re.compile(r"\binvestment objectives?\b|\bobjectives?\b")
_MANAGER = re.compile(r"\bfund managers?\b|\bwho manages\b|\bwho is the manager\b")
_MANAGER_DETAIL = re.compile(r"\b(?:in )?more detail\b|\bbiograph|\bbackground\b")


@dataclass(frozen=True)
class Resolution:
    kind: str
    scheme_ids: tuple[str, ...] = ()
    field: str | None = None
    fields: tuple[str, ...] = ()
    topic: str | None = None
    ambiguous: bool = False


def resolve(question: str, prior_scheme_id: str | None = None) -> Resolution:
    """Resolve scheme aliases and the field or topic the question asks for.

    ``prior_scheme_id`` is used only when the question names no scheme and still
    asks for a scheme fact. "Cap fund" matches no alias. More than two named
    schemes is ambiguous. An ELSS question that names one of these schemes reads
    that scheme's category and exit load; it does not select the general
    ``elss_lock_in`` topic.
    """
    text = _normalize(question or "")
    if _STATEMENT.search(text):
        return Resolution(kind="statement_download", topic="statement_download")

    named = _match_schemes(text)
    prior = prior_scheme_id or None

    if _ELSS.search(text) or _LOCK_IN.search(text):
        return _resolve_lock_in(text, named, prior)

    if not named and _is_definition(text):
        return Resolution(kind="definition", topic="definition")

    if len(named) > 2:
        return Resolution(kind="ambiguous", field=_first_field(text), ambiguous=True)

    if _HOLDINGS.search(text):
        return Resolution(kind="holdings", scheme_ids=_schemes(named, prior), field="holdings")

    if _OBJECTIVE.search(text):
        return Resolution(
            kind="prose",
            scheme_ids=_schemes(named, prior),
            topic="objective",
        )

    if _MANAGER.search(text) and _MANAGER_DETAIL.search(text):
        return Resolution(
            kind="prose",
            scheme_ids=_schemes(named, prior),
            topic="fund_manager",
        )

    field = _first_field(text)
    if field:
        return Resolution(kind="field", scheme_ids=_schemes(named, prior), field=field)

    return Resolution(kind="unknown", scheme_ids=tuple(named))


def _resolve_lock_in(text: str, named: list[str], prior: str | None) -> Resolution:
    if len(named) > 2:
        return Resolution(kind="ambiguous", ambiguous=True)
    if named:
        return Resolution(
            kind="scheme_lock_in",
            scheme_ids=tuple(named),
            fields=("category", "exit_load"),
        )
    # A general ELSS question stays general even when the client sent a prior scheme.
    if _ELSS.search(text) or not prior:
        return Resolution(kind="elss_lock_in", topic="elss_lock_in")
    return Resolution(
        kind="scheme_lock_in",
        scheme_ids=(prior,),
        fields=("category", "exit_load"),
    )


def _schemes(named: list[str], prior: str | None) -> tuple[str, ...]:
    if named:
        return tuple(named)
    if prior:
        return (prior,)
    return ()


def _is_definition(text: str) -> bool:
    return _DEFINABLE.search(text) is not None and _DEFINITION.search(text) is not None


def _first_field(text: str) -> str | None:
    found: tuple[int, str] | None = None
    for field, pattern in _FIELD_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        if found is None or match.start() < found[0]:
            found = (match.start(), field)
    if found is None:
        return None
    return found[1]


def _match_schemes(text: str) -> list[str]:
    found: list[tuple[int, str]] = []
    for scheme in SCHEMES:
        earliest: int | None = None
        for alias in scheme.aliases:
            position = _phrase_index(text, alias)
            if position is None:
                continue
            if earliest is None or position < earliest:
                earliest = position
        if earliest is not None:
            found.append((earliest, scheme.scheme_id))
    found.sort(key=lambda item: item[0])
    return [scheme_id for _, scheme_id in found]


def _phrase_index(text: str, alias: str) -> int | None:
    needle = _normalize(alias)
    if not needle:
        return None
    parts = [re.escape(part) for part in needle.split(" ")]
    pattern = r"(?<![a-z0-9])" + r"\s+".join(parts) + r"(?![a-z0-9])"
    match = re.search(pattern, text)
    if match is None:
        return None
    return match.start()


def _normalize(text: str) -> str:
    lowered = text.lower().replace("-", " ").replace("_", " ")
    cleaned = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()
