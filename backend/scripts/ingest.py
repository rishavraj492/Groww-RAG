"""Ingest allowlisted corpus pages into scheme_facts.json and passages.json.

`--source fixture` reads saved HTML and does not use the network.
`--source live` fetches allowlisted URLs and stores the raw body by URL hash.
Official factsheets and SIDs are merged over Groww fields. A SID link found on
a scheme page may be fetched once in the same live run when its host is
allowlisted. Regulatory pages become passages and do not overwrite scheme facts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml
from bs4 import BeautifulSoup

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.config import EMBEDDING_MODEL, HOLDINGS_CAP
from app.services.facts import load_facts
from app.services.official import (
    extract_official_fields,
    extract_pdf_text,
    is_scheme_official_doc,
    merge_official_fields,
)
from app.services.passages import chunk_general_html, chunk_scheme_html
from app.services.registry import REQUIRED_GROWW_URLS, SCHEME_BY_ID

DATA_DIR = _BACKEND_DIR / "data"
DEFAULT_SOURCES = DATA_DIR / "sources.yaml"
DEFAULT_FACTS_PATH = DATA_DIR / "scheme_facts.json"
DEFAULT_MANIFEST_PATH = DATA_DIR / "manifest.json"
DEFAULT_FIXTURES = DATA_DIR / "fixtures"
DEFAULT_RAW = DATA_DIR / "raw"

ALLOWED_HOSTS = frozenset(
    {
        "groww.in",
        "www.hdfcfund.com",
        "www.sebi.gov.in",
        "investor.sebi.gov.in",
        "www.amfiindia.com",
    }
)

USER_AGENT = "FactsOnlyMutualFundFAQ/1.0 (educational corpus ingest; facts-only HDFC scheme FAQ)"
FETCH_TIMEOUT_SECONDS = 20.0
MIN_REQUEST_INTERVAL_SECONDS = 1.0

FACT_FIELDS = (
    "scheme_id",
    "name",
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
    "holdings",
    "source_url",
    "authority",
    "accessed_at",
    "sid_url",
)

_SCALAR_FIELDS = (
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

# Longer labels first so "fund size (aum)" wins over "fund size" and "aum".
_LABELS: tuple[tuple[str, str], ...] = (
    ("min. for 2nd investment", "minimum_additional"),
    ("min. for 1st investment", "minimum_lumpsum"),
    ("current fund manager", "fund_manager"),
    ("min. for sip", "minimum_sip"),
    ("fund size (aum)", "aum"),
    ("tax implication", "tax_note"),
    ("expense ratio", "expense_ratio"),
    ("fund benchmark", "benchmark"),
    ("minimum lump sum", "minimum_lumpsum"),
    ("minimum sip", "minimum_sip"),
    ("min. sip amount", "minimum_sip"),
    ("stamp duty", "stamp_duty"),
    ("fund manager", "fund_manager"),
    ("exit load", "exit_load"),
    ("riskometer", "riskometer"),
    ("fund size", "aum"),
    ("benchmark", "benchmark"),
    ("category", "category"),
    ("risk", "riskometer"),
    ("nav", "nav_value"),
    ("aum", "aum"),
)

_EXCLUDED_HEADING = re.compile(
    r"^(about|returns|trailing returns|annualised returns|annualized returns|"
    r"rank|ranking|rank table|calculator|return calculator)\b",
    re.I,
)

_EMBEDDED_FIELDS = {
    "expenseratio": "expense_ratio",
    "exitload": "exit_load",
    "minforsip": "minimum_sip",
    "minimumsip": "minimum_sip",
    "minsip": "minimum_sip",
    "minsipamount": "minimum_sip",
    "minsipinvestment": "minimum_sip",
    "minfor1stinvestment": "minimum_lumpsum",
    "minimumlumpsum": "minimum_lumpsum",
    "minlumpsum": "minimum_lumpsum",
    "mininvestmentamount": "minimum_lumpsum",
    "minfor2ndinvestment": "minimum_additional",
    "minimumadditional": "minimum_additional",
    "miniadditionalinvestment": "minimum_additional",
    "nav": "nav_value",
    "navvalue": "nav_value",
    "navdate": "nav_date",
    "aum": "aum",
    "fundsize": "aum",
    "fundsizeaum": "aum",
    "benchmark": "benchmark",
    "fundbenchmark": "benchmark",
    "category": "category",
    "riskometer": "riskometer",
    "risk": "riskometer",
    "risklabel": "riskometer",
    "fundmanager": "fund_manager",
    "currentfundmanager": "fund_manager",
    "stampduty": "stamp_duty",
    "taxnote": "tax_note",
    "taximplication": "tax_note",
    "taximpact": "tax_note",
    "holdings": "holdings",
    "topholdings": "holdings",
}

_SKIP_EMBEDDED_SUBTREES = frozenset(
    {
        "about",
        "description",
        "overview",
        "returns",
        "returncalculator",
        "calculator",
        "rank",
        "ranking",
        "annualisedreturns",
        "annualizedreturns",
        "peercomparison",
        "amcinfo",
        "analysis",
        "historicexitloads",
        "historicfundexpense",
        "simplereturn",
        "sipreturn",
    }
)

_CORE_EMBEDDED = frozenset(
    {"expense_ratio", "exit_load", "aum", "nav_value", "minimum_sip", "benchmark"}
)

_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

_RUPEE_AMOUNT = re.compile(r"₹\s*[\d,]+(?:\.\d+)?|Rs\.?\s*[\d,]+(?:\.\d+)?", re.I)


class IngestError(Exception):
    """The catalog is invalid, so ingest stops before any fetch."""


def load_sources(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        sources = data.get("sources", [])
    elif isinstance(data, list):
        sources = data
    else:
        sources = []
    if not isinstance(sources, list):
        raise IngestError(f"{path} has no sources")
    return sources


def validate_sources(sources: list[dict]) -> None:
    """Reject a bad catalog before any network call."""
    errors: list[str] = []
    seen_urls: set[str] = set()
    if not sources:
        errors.append("sources.yaml has no sources")
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            errors.append(f"source {index} is not an object")
            continue
        url = source.get("url")
        if not isinstance(url, str) or not url:
            errors.append(f"source {index} is missing a url")
            continue
        host = urlparse(url).hostname
        if host not in ALLOWED_HOSTS:
            errors.append(f"URL host is not allowlisted: {url}")
        seen_urls.add(url)
        document_type = source.get("document_type")
        scheme_id = source.get("scheme_id") or ""
        if document_type == "scheme_page" and scheme_id not in SCHEME_BY_ID:
            errors.append(f"unknown scheme_id for {url}")
        if is_scheme_official_doc(document_type) and scheme_id not in SCHEME_BY_ID:
            errors.append(f"official document needs a known scheme_id: {url}")
    for url in REQUIRED_GROWW_URLS:
        if url not in seen_urls:
            errors.append(f"missing required Groww URL: {url}")
    if errors:
        raise IngestError("\n".join(errors))


def default_client_factory() -> httpx.Client:
    return httpx.Client(
        timeout=FETCH_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )


def parse_scheme_html(
    html: str,
    *,
    scheme_id: str,
    source_url: str,
    authority: str,
    accessed_at: str,
) -> dict:
    scheme = SCHEME_BY_ID.get(scheme_id)
    if scheme is None:
        raise IngestError(f"unknown scheme_id: {scheme_id}")
    record = _empty_record(scheme.name, scheme_id, source_url, authority, accessed_at)
    soup = BeautifulSoup(html, "html.parser")
    embedded = _embedded_facts(soup)
    _drop_excluded_sections(soup)
    labeled = _extract_labels(soup)
    for field, value in _extract_adjacent_labels(soup).items():
        labeled.setdefault(field, value)
    if embedded is not None:
        for field in _SCALAR_FIELDS:
            if embedded.get(field):
                record[field] = _present_fact_value(field, embedded[field])
            elif labeled.get(field):
                record[field] = labeled[field]
        record["holdings"] = embedded.get("holdings") or _extract_holdings(soup)
    else:
        for field, value in labeled.items():
            if field in _SCALAR_FIELDS and value:
                record[field] = value
        record["holdings"] = _extract_holdings(soup)
        nav_date = _nav_date(soup) or labeled.get("nav_date")
        if nav_date and record["nav_value"]:
            record["nav_date"] = nav_date
            amount = _RUPEE_AMOUNT.search(record["nav_value"])
            if amount:
                record["nav_value"] = re.sub(r"\s+", "", amount.group(0))
    if not record["riskometer"]:
        record["riskometer"] = _risk_label(soup) or _risk_phrase(soup)
    if not record["category"]:
        record["category"] = _category_chips(soup)
    if not record["nav_date"] and labeled.get("nav_date"):
        record["nav_date"] = labeled["nav_date"]
    if not record["nav_date"] and record["nav_value"]:
        found = _find_date(record["nav_value"])
        if found:
            record["nav_date"] = found
    record["sid_url"] = _sid_url(soup)
    record["holdings"] = record["holdings"][:HOLDINGS_CAP]
    return {field: record[field] for field in FACT_FIELDS}


def run_ingest(
    source_mode: str,
    sources_path: Path | None = None,
    facts_path: Path | None = None,
    manifest_path: Path | None = None,
    fixtures_dir: Path | None = None,
    raw_dir: Path | None = None,
    accessed_at: str | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    client_factory: Callable[[], httpx.Client] | None = None,
    chroma_path: Path | None = None,
    embedder: object | None = None,
) -> dict:
    sources_path = sources_path or DEFAULT_SOURCES
    facts_path = facts_path or DEFAULT_FACTS_PATH
    manifest_path = manifest_path or DEFAULT_MANIFEST_PATH
    fixtures_dir = fixtures_dir or DEFAULT_FIXTURES
    raw_dir = raw_dir or DEFAULT_RAW
    accessed_at = accessed_at or datetime.now(timezone.utc).date().isoformat()

    sources = load_sources(sources_path)
    validate_sources(sources)
    previous = _load_previous(facts_path)
    passages_path = facts_path.with_name("passages.json")
    previous_passages = _load_previous_passages(passages_path)

    if source_mode == "fixture":
        schemes, manifest_entries, passages = _ingest_fixtures(
            sources, fixtures_dir, accessed_at, previous, previous_passages
        )
    elif source_mode == "live":
        factory = client_factory or default_client_factory
        schemes, manifest_entries, passages = _ingest_live(
            sources,
            raw_dir,
            accessed_at,
            previous,
            previous_passages,
            factory,
            sleep,
            monotonic,
        )
    else:
        raise IngestError(f"unknown source mode: {source_mode}")

    model_name = _index_passages(chroma_path, passages, embedder)
    payload = {"schemes": schemes}
    manifest = {
        "accessed_at": accessed_at,
        "source_mode": source_mode,
        "passage_count": len(passages),
        "sources": manifest_entries,
    }
    if model_name:
        manifest["embedding_model"] = model_name
    _write_json(facts_path, payload)
    _write_json(manifest_path, manifest)
    _write_json(passages_path, {"passages": passages})
    return {"schemes": schemes, "manifest": manifest, "passages": passages}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest scheme pages into scheme_facts.json")
    parser.add_argument("--source", required=True, choices=("fixture", "live"))
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--facts", type=Path, default=DEFAULT_FACTS_PATH)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    args = parser.parse_args(argv)
    from app.config import CHROMA_PATH

    try:
        result = run_ingest(
            args.source,
            sources_path=args.sources,
            facts_path=args.facts,
            manifest_path=args.manifest,
            chroma_path=CHROMA_PATH,
        )
    except IngestError as exc:
        print(exc, file=sys.stderr)
        return 1
    model_name = result["manifest"].get("embedding_model")
    indexed = f" with {model_name}" if model_name else ""
    print(
        f"Wrote {len(result['schemes'])} scheme records to {args.facts} "
        f"and {len(result['passages'])} passages{indexed}"
    )
    return 0


def _index_passages(chroma_path: Path | None, passages: list[dict], embedder: object | None) -> str | None:
    """Embed and replace URL rows when a Chroma directory is set. Tests pass a fake embedder."""
    if chroma_path is None:
        return None
    active = embedder
    if active is None:
        from app.services.embeddings import build_embedder

        active = build_embedder(EMBEDDING_MODEL)
    from app.services.index import index_passages

    index_passages(chroma_path, passages, active)
    model_name = getattr(active, "model_name", None)
    if isinstance(model_name, str) and model_name:
        return model_name
    return EMBEDDING_MODEL


def _ingest_fixtures(
    sources: list[dict],
    fixtures_dir: Path,
    accessed_at: str,
    previous: dict[str, dict],
    previous_passages: dict[str, list[dict]],
) -> tuple[list[dict], list[dict], list[dict]]:
    schemes_by_id: dict[str, dict] = {}
    entries: list[dict] = []
    passages: list[dict] = []
    by_url_previous = previous

    for source in sources:
        if source.get("document_type") != "scheme_page":
            continue
        entry = _manifest_entry(source)
        scheme_id = source.get("scheme_id")
        url = source["url"]
        if not isinstance(scheme_id, str) or scheme_id not in SCHEME_BY_ID:
            entry["status"] = "failed"
            entry["error"] = "unknown scheme_id"
            entries.append(entry)
            continue
        path = _fixture_path(fixtures_dir, source)
        if path is None or not path.is_file():
            entry["status"] = "failed"
            entry["error"] = "saved HTML fixture not found"
            entries.append(entry)
            _restore_previous_scheme(schemes_by_id, by_url_previous, url)
            _keep_previous_passages(passages, previous_passages, url)
            continue
        html = path.read_text(encoding="utf-8")
        record = parse_scheme_html(
            html,
            scheme_id=scheme_id,
            source_url=url,
            authority=source.get("authority") or "platform",
            accessed_at=accessed_at,
        )
        if not _record_has_facts(record):
            entry["status"] = "failed"
            entry["error"] = "no labeled facts in saved HTML"
            entries.append(entry)
            _restore_previous_scheme(schemes_by_id, by_url_previous, url)
            _keep_previous_passages(passages, previous_passages, url)
            continue
        entry["status"] = "ok"
        entries.append(entry)
        schemes_by_id[scheme_id] = record
        passages.extend(_passages_for_scheme_page(source, html, record))

    for source in sources:
        document_type = source.get("document_type")
        if is_scheme_official_doc(document_type):
            entry, body = _load_fixture_body(source, fixtures_dir)
            if body is None:
                entries.append(entry)
                _keep_previous_passages(passages, previous_passages, source["url"])
                continue
            _apply_official_body(source, body, schemes_by_id, entry, accessed_at)
            entries.append(entry)
            continue
        if document_type in {"regulatory", "help"}:
            entry, body = _load_fixture_body(source, fixtures_dir)
            if body is None:
                entries.append(entry)
                _keep_previous_passages(passages, previous_passages, source["url"])
                continue
            if isinstance(body, bytes):
                text = body.decode("utf-8", errors="replace")
            else:
                text = body
            general = _passages_for_general(source, text, accessed_at)
            if not general:
                entry["status"] = "failed"
                entry["error"] = "no passages in saved document"
                entries.append(entry)
                _keep_previous_passages(passages, previous_passages, source["url"])
                continue
            entry["status"] = "ok"
            entries.append(entry)
            passages.extend(general)
            continue
        if document_type != "scheme_page":
            entry = _manifest_entry(source)
            entry["status"] = "failed"
            entry["error"] = "saved HTML fixture not found"
            entries.append(entry)

    return list(schemes_by_id.values()), entries, passages


def _ingest_live(
    sources: list[dict],
    raw_dir: Path,
    accessed_at: str,
    previous: dict[str, dict],
    previous_passages: dict[str, list[dict]],
    client_factory: Callable[[], httpx.Client],
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
) -> tuple[list[dict], list[dict], list[dict]]:
    schemes_by_id: dict[str, dict] = {}
    entries: list[dict] = []
    passages: list[dict] = []
    fetched: set[str] = set()
    last_request_at: float | None = None

    def paced_fetch(client: httpx.Client, url: str) -> bytes:
        nonlocal last_request_at
        if last_request_at is not None:
            elapsed = monotonic() - last_request_at
            if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
                sleep(MIN_REQUEST_INTERVAL_SECONDS - elapsed)
        last_request_at = monotonic()
        body = _fetch_body(client, url)
        fetched.add(url)
        return body

    with client_factory() as client:
        for source in sources:
            if source.get("document_type") != "scheme_page":
                continue
            entry = _manifest_entry(source)
            url = source["url"]
            scheme_id = source.get("scheme_id")
            try:
                body = paced_fetch(client, url)
            except Exception as exc:
                entry["status"] = "failed"
                entry["error"] = _short_error(exc)
                entries.append(entry)
                _restore_previous_scheme(schemes_by_id, previous, url)
                _keep_previous_passages(passages, previous_passages, url)
                continue
            _write_raw(raw_dir, url, body)
            if not isinstance(scheme_id, str) or scheme_id not in SCHEME_BY_ID:
                entry["status"] = "failed"
                entry["error"] = "unknown scheme_id"
                entries.append(entry)
                continue
            html = body.decode("utf-8", errors="replace")
            record = parse_scheme_html(
                html,
                scheme_id=scheme_id,
                source_url=url,
                authority=source.get("authority") or "platform",
                accessed_at=accessed_at,
            )
            if not _record_has_facts(record):
                entry["status"] = "failed"
                entry["error"] = "no labeled facts in page"
                entries.append(entry)
                _restore_previous_scheme(schemes_by_id, previous, url)
                _keep_previous_passages(passages, previous_passages, url)
                continue
            entry["status"] = "ok"
            entries.append(entry)
            schemes_by_id[scheme_id] = record
            passages.extend(_passages_for_scheme_page(source, html, record))

        for source in sources:
            document_type = source.get("document_type")
            if document_type == "scheme_page":
                continue
            entry = _manifest_entry(source)
            url = source["url"]
            try:
                body = paced_fetch(client, url)
            except Exception as exc:
                entry["status"] = "failed"
                entry["error"] = _short_error(exc)
                entries.append(entry)
                _keep_previous_passages(passages, previous_passages, url)
                continue
            _write_raw(raw_dir, url, body)
            if is_scheme_official_doc(document_type):
                _apply_official_body(source, body, schemes_by_id, entry, accessed_at)
                entries.append(entry)
                continue
            if document_type in {"regulatory", "help"}:
                text = _body_as_text(body)
                if text is None:
                    entry["status"] = "failed"
                    entry["error"] = "PDF has no text layer"
                    entries.append(entry)
                    continue
                general = _passages_for_general(source, text, accessed_at)
                if not general:
                    entry["status"] = "failed"
                    entry["error"] = "no passages in document"
                    entries.append(entry)
                    _keep_previous_passages(passages, previous_passages, url)
                    continue
                entry["status"] = "ok"
                entries.append(entry)
                passages.extend(general)
                continue
            entry["status"] = "failed"
            entry["error"] = "no scheme facts extracted from this document type"
            entries.append(entry)
            _keep_previous_passages(passages, previous_passages, url)

        _fetch_one_hop_sids(
            client,
            schemes_by_id,
            entries,
            passages,
            fetched,
            raw_dir,
            accessed_at,
            paced_fetch,
        )

    return list(schemes_by_id.values()), entries, passages


def _fetch_one_hop_sids(
    client: httpx.Client,
    schemes_by_id: dict[str, dict],
    entries: list[dict],
    passages: list[dict],
    fetched: set[str],
    raw_dir: Path,
    accessed_at: str,
    paced_fetch: Callable[[httpx.Client, str], bytes],
) -> None:
    """Fetch a SID linked from a scheme page once. Do not follow links from the SID."""
    pending: list[tuple[str, str]] = []
    for scheme_id, record in list(schemes_by_id.items()):
        sid_url = record.get("sid_url")
        if not isinstance(sid_url, str) or not sid_url:
            continue
        host = urlparse(sid_url).hostname
        if host not in ALLOWED_HOSTS:
            continue
        if sid_url in fetched:
            continue
        pending.append((scheme_id, sid_url))

    for scheme_id, sid_url in pending:
        source = {
            "url": sid_url,
            "scheme_id": scheme_id,
            "document_type": "sid",
            "authority": "official",
        }
        entry = _manifest_entry(source)
        try:
            body = paced_fetch(client, sid_url)
        except Exception as exc:
            entry["status"] = "failed"
            entry["error"] = _short_error(exc)
            entries.append(entry)
            continue
        _write_raw(raw_dir, sid_url, body)
        _apply_official_body(source, body, schemes_by_id, entry, accessed_at)
        entries.append(entry)


def _apply_official_body(
    source: dict,
    body: str | bytes,
    schemes_by_id: dict[str, dict],
    entry: dict,
    accessed_at: str,
) -> None:
    """Merge official fields into the scheme record. Definition pages never call this."""
    scheme_id = source.get("scheme_id")
    url = source["url"]
    if not isinstance(scheme_id, str) or scheme_id not in SCHEME_BY_ID:
        entry["status"] = "failed"
        entry["error"] = "unknown scheme_id"
        return
    if isinstance(body, bytes) and body.lstrip().startswith(b"%PDF"):
        if extract_pdf_text(body) is None:
            entry["status"] = "failed"
            entry["error"] = "PDF has no text layer"
            return
    fields = extract_official_fields(body)
    if not fields:
        entry["status"] = "failed"
        entry["error"] = "no labeled facts in official document"
        return
    platform = schemes_by_id.get(scheme_id)
    if platform is None:
        scheme = SCHEME_BY_ID[scheme_id]
        platform = _empty_record(
            scheme.name,
            scheme_id,
            url,
            source.get("authority") or "official",
            accessed_at,
        )
    merged, platform_value = merge_official_fields(
        platform,
        fields,
        official_url=url,
        authority=source.get("authority") or "official",
    )
    merged["accessed_at"] = accessed_at
    if platform.get("sid_url") and not merged.get("sid_url"):
        merged["sid_url"] = platform.get("sid_url")
    schemes_by_id[scheme_id] = merged
    entry["status"] = "ok"
    if platform_value:
        entry["conflict"] = True
        entry["platform_value"] = platform_value


def _load_fixture_body(source: dict, fixtures_dir: Path) -> tuple[dict, str | bytes | None]:
    entry = _manifest_entry(source)
    path = _fixture_path(fixtures_dir, source)
    if path is None or not path.is_file():
        entry["status"] = "failed"
        entry["error"] = "saved HTML fixture not found"
        return entry, None
    if path.suffix.casefold() == ".pdf":
        return entry, path.read_bytes()
    return entry, path.read_text(encoding="utf-8")


def _fixture_path(fixtures_dir: Path, source: dict) -> Path | None:
    named = source.get("fixture")
    if isinstance(named, str) and named:
        return fixtures_dir / named
    document_type = source.get("document_type") or ""
    scheme_id = source.get("scheme_id") or ""
    topic = source.get("topic") or ""
    if document_type == "scheme_page" and scheme_id:
        return fixtures_dir / f"{scheme_id.replace('-', '_')}.html"
    if is_scheme_official_doc(document_type) and scheme_id:
        return fixtures_dir / f"{scheme_id.replace('-', '_')}_{document_type}.html"
    if document_type in {"regulatory", "help"}:
        stem = topic or document_type
        return fixtures_dir / f"{stem.replace('-', '_')}.html"
    return None


def _passages_for_scheme_page(source: dict, html: str, record: dict) -> list[dict]:
    scheme_id = source.get("scheme_id")
    if not isinstance(scheme_id, str):
        return []
    scheme = SCHEME_BY_ID.get(scheme_id)
    if scheme is None:
        return []
    return chunk_scheme_html(
        html,
        scheme_id=scheme_id,
        source_url=source["url"],
        title=scheme.name,
        authority=source.get("authority") or "platform",
        document_type=source.get("document_type") or "scheme_page",
        accessed_at=record["accessed_at"],
        as_of=record.get("nav_date"),
    )


def _passages_for_general(source: dict, html: str, accessed_at: str) -> list[dict]:
    title = source.get("title") or source.get("topic") or source.get("document_type") or "Source"
    if isinstance(title, str) is False:
        title = "Source"
    return chunk_general_html(
        html,
        source_url=source["url"],
        title=str(title),
        authority=source.get("authority") or "official",
        document_type=source.get("document_type") or "regulatory",
        topic=source.get("topic") or "other",
        accessed_at=accessed_at,
        scheme_id=source.get("scheme_id") or "",
    )


def _body_as_text(body: bytes) -> str | None:
    if body.lstrip().startswith(b"%PDF"):
        return extract_pdf_text(body)
    return body.decode("utf-8", errors="replace")


def _fetch_body(client: httpx.Client, url: str) -> bytes:
    response = client.get(url, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    final_host = urlparse(str(response.url)).hostname
    if final_host not in ALLOWED_HOSTS:
        raise IngestError(f"response host is not allowlisted: {response.url}")
    return response.content


def _fetch_page(client: httpx.Client, url: str) -> str:
    """Compatibility helper for tests that still expect decoded HTML."""
    return _fetch_body(client, url).decode("utf-8", errors="replace")


def _restore_previous_scheme(
    schemes_by_id: dict[str, dict],
    previous: dict[str, dict],
    url: str,
) -> None:
    record = previous.get(url)
    if record is None:
        return
    scheme_id = record.get("scheme_id")
    if isinstance(scheme_id, str) and scheme_id:
        schemes_by_id.setdefault(scheme_id, record)


def _write_raw(raw_dir: Path, url: str, body: str | bytes) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    path = raw_dir / digest
    if isinstance(body, bytes):
        path.write_bytes(body)
    else:
        path.write_text(body, encoding="utf-8")


def _empty_record(name: str, scheme_id: str, source_url: str, authority: str, accessed_at: str) -> dict:
    return {
        "scheme_id": scheme_id,
        "name": name,
        "category": None,
        "riskometer": None,
        "expense_ratio": None,
        "exit_load": None,
        "minimum_sip": None,
        "minimum_lumpsum": None,
        "minimum_additional": None,
        "nav_value": None,
        "nav_date": None,
        "aum": None,
        "benchmark": None,
        "fund_manager": None,
        "stamp_duty": None,
        "tax_note": None,
        "holdings": [],
        "source_url": source_url,
        "authority": authority,
        "accessed_at": accessed_at,
        "sid_url": None,
    }


def _record_has_facts(record: dict) -> bool:
    if any(record.get(field) for field in _SCALAR_FIELDS):
        return True
    return bool(record.get("holdings"))


def _drop_excluded_sections(soup: BeautifulSoup) -> None:
    """Remove About, return, rank, and calculator sections before fact extraction.

    The About paragraph restates fund size and can disagree with the labeled AUM.
    Return tables, rank tables, and calculator output are not facts.
    """
    for heading in list(soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])):
        if heading.parent is None:
            continue
        title = " ".join(heading.get_text(" ", strip=True).split())
        if not _EXCLUDED_HEADING.match(title):
            continue
        section = heading.find_parent("section")
        if section is not None:
            section.decompose()
            continue
        level = int(heading.name[1])
        for sibling in list(heading.next_siblings):
            name = getattr(sibling, "name", None)
            if name in {"h1", "h2", "h3", "h4", "h5", "h6"} and int(name[1]) <= level:
                break
            sibling.extract()
        heading.decompose()


def _extract_labels(soup: BeautifulSoup) -> dict[str, str]:
    found: dict[str, str] = {}
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        field = _match_label(cells[0].get_text(" ", strip=True))
        if field is None or field in found:
            continue
        value = _clean_text(cells[1].get_text(" ", strip=True))
        if value:
            found[field] = value
    for term in soup.find_all("dt"):
        field = _match_label(term.get_text(" ", strip=True))
        definition = term.find_next_sibling("dd")
        if field is None or field in found or definition is None:
            continue
        value = _clean_text(definition.get_text(" ", strip=True))
        if value:
            found[field] = value
    for label in soup.find_all(class_="label"):
        field = _match_label(label.get_text(" ", strip=True))
        if field is None or field in found:
            continue
        value_node = label.find_next_sibling(class_="value")
        if value_node is None:
            value_node = _next_element_sibling(label)
        if value_node is None:
            continue
        value = _clean_text(value_node.get_text(" ", strip=True))
        if value:
            found[field] = value
    return found


def _match_label(text: str) -> str | None:
    normalized = _normalize_label(text)
    for label, field in _LABELS:
        if normalized == label:
            return field
    return None


def _normalize_label(text: str) -> str:
    collapsed = " ".join(text.replace("\xa0", " ").split()).casefold()
    return collapsed.rstrip(":").strip()


def _clean_text(text: str | None) -> str | None:
    if text is None:
        return None
    collapsed = " ".join(str(text).replace("\xa0", " ").split())
    return collapsed or None


def _next_element_sibling(node):
    sibling = node.next_sibling
    while sibling is not None and not getattr(sibling, "name", None):
        sibling = sibling.next_sibling
    return sibling


def _risk_label(soup: BeautifulSoup) -> str | None:
    node = soup.select_one(".risk-label, .riskometer")
    if node is None:
        return None
    text = _clean_text(node.get_text(" ", strip=True))
    if not text:
        return None
    return re.sub(r"\s+risk$", "", text, flags=re.I).strip() or None


def _category_chips(soup: BeautifulSoup) -> str | None:
    chips = soup.select(".category-chips .chip")
    names = [_clean_text(chip.get_text(" ", strip=True)) for chip in chips]
    names = [name for name in names if name]
    if not names:
        return None
    return " - ".join(names)


def _nav_date(soup: BeautifulSoup) -> str | None:
    for label in soup.find_all(class_="label"):
        if _match_label(label.get_text(" ", strip=True)) != "nav_value":
            continue
        parent = label.parent
        if parent is None:
            continue
        as_of = parent.select_one(".as-of")
        if as_of is None:
            continue
        found = _find_date(as_of.get_text(" ", strip=True))
        if found:
            return found
    return None


def _find_date(text: str) -> str | None:
    if not text:
        return None
    cleaned = " ".join(text.replace(",", " ").split())
    iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", cleaned)
    if iso:
        return f"{iso.group(1)}-{iso.group(2)}-{iso.group(3)}"
    day_first = re.search(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b", cleaned)
    if day_first:
        month = _MONTHS.get(day_first.group(2).casefold())
        if month:
            return f"{int(day_first.group(3)):04d}-{month:02d}-{int(day_first.group(1)):02d}"
    month_first = re.search(r"\b([A-Za-z]{3,9})\s+(\d{1,2})\s+(\d{4})\b", cleaned)
    if month_first:
        month = _MONTHS.get(month_first.group(1).casefold())
        if month:
            return f"{int(month_first.group(3)):04d}-{month:02d}-{int(month_first.group(2)):02d}"
    day_hyphen = re.search(r"\b(\d{1,2})-([A-Za-z]{3,9})-(\d{2,4})\b", cleaned)
    if day_hyphen:
        month = _MONTHS.get(day_hyphen.group(2).casefold())
        if month:
            return f"{_year(day_hyphen.group(3)):04d}-{month:02d}-{int(day_hyphen.group(1)):02d}"
    day_tick = re.search(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+'(\d{2})\b", cleaned)
    if day_tick:
        month = _MONTHS.get(day_tick.group(2).casefold())
        if month:
            return f"{_year(day_tick.group(3)):04d}-{month:02d}-{int(day_tick.group(1)):02d}"
    numeric = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", cleaned)
    if numeric:
        return f"{int(numeric.group(3)):04d}-{int(numeric.group(2)):02d}-{int(numeric.group(1)):02d}"
    return None


def _year(raw: str) -> int:
    year = int(raw)
    if year < 100:
        return 2000 + year
    return year


_PLAIN_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_RISK_PHRASE = re.compile(
    r"^(Very High|Moderately High|Low to Moderate|Moderate|Low)(?:\s+Risk)?$",
    re.I,
)


def _present_fact_value(field: str, value: str) -> str:
    """Turn Groww's raw JSON numbers into the labeled strings shown on the page."""
    text = _clean_text(value) or ""
    if field == "nav_date":
        return _find_date(text) or text
    if field == "riskometer":
        return re.sub(r"\s+risk$", "", text, flags=re.I).strip()
    if not _PLAIN_NUMBER.fullmatch(text):
        return text
    number = float(text)
    if field == "expense_ratio":
        return f"{number:.2f}%"
    if field in {"minimum_sip", "minimum_lumpsum", "minimum_additional"}:
        if number.is_integer():
            return f"₹{int(number):,}"
        return f"₹{number:,.2f}"
    if field == "nav_value":
        return f"₹{number:,.2f}"
    if field == "aum":
        return f"₹{number:,.2f} Cr"
    return text


def _present_weight(value: str | None) -> str:
    text = _clean_text(value) or ""
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return f"{float(text):.2f}%"
    return text


def _extract_adjacent_labels(soup: BeautifulSoup) -> dict[str, str]:
    """Read Groww's label element followed by its value element."""
    found: dict[str, str] = {}
    for node in soup.find_all(True):
        text = _clean_text(node.get_text(" ", strip=True))
        if not text or len(text) > 40:
            continue
        field = None
        if text.casefold().startswith("nav"):
            field = "nav_value"
            date = _find_date(text)
            if date:
                found.setdefault("nav_date", date)
        else:
            field = _match_label(text)
        if field is None or field in found:
            continue
        sibling = _next_element_sibling(node)
        if sibling is None:
            continue
        value = _clean_text(sibling.get_text(" ", strip=True))
        if not value or len(value) > 500:
            continue
        if value.casefold().startswith(("a fee ", "a percentage ", "a form of ")):
            continue
        found[field] = value
    return found


def _risk_phrase(soup: BeautifulSoup) -> str | None:
    for node in soup.find_all(True):
        text = _clean_text(node.get_text(" ", strip=True))
        if not text or len(text) > 40:
            continue
        match = _RISK_PHRASE.fullmatch(text)
        if match:
            return match.group(1).strip()
    return None


def _extract_holdings(soup: BeautifulSoup) -> list[dict]:
    tables = []
    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        if re.search(r"holding", heading.get_text(" ", strip=True), re.I):
            section = heading.find_parent("section")
            scope = section if section is not None else heading.parent
            if scope is not None:
                tables.extend(scope.find_all("table"))
    if not tables:
        tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [_normalize_label(cell.get_text(" ", strip=True)) for cell in rows[0].find_all(["th", "td"])]
        if any("return" in header or header in {"period", "1y", "3y", "5y"} for header in headers):
            continue
        name_index = _header_index(headers, ("name", "company", "stock"))
        if name_index is None:
            continue
        sector_index = _header_index(headers, ("sector",))
        weight_index = _header_index(headers, ("weight", "assets", "allocation"))
        holdings = []
        for row in rows[1:]:
            cells = [_clean_text(cell.get_text(" ", strip=True)) or "" for cell in row.find_all(["td", "th"])]
            if name_index >= len(cells) or not cells[name_index]:
                continue
            holdings.append(
                {
                    "name": cells[name_index],
                    "sector": cells[sector_index] if sector_index is not None and sector_index < len(cells) else "",
                    "weight": cells[weight_index] if weight_index is not None and weight_index < len(cells) else "",
                }
            )
            if len(holdings) >= HOLDINGS_CAP:
                break
        if holdings:
            return holdings
    return []


def _header_index(headers: list[str], options: tuple[str, ...]) -> int | None:
    for index, header in enumerate(headers):
        if any(option == header or option in header for option in options):
            return index
    return None


def _sid_url(soup: BeautifulSoup) -> str | None:
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        host = urlparse(href).hostname
        if host not in ALLOWED_HOSTS or host == "groww.in":
            continue
        label = anchor.get_text(" ", strip=True).casefold()
        href_key = href.casefold()
        if "scheme information" in label or re.search(r"\bsid\b", label) or "sid" in href_key:
            return href
    return None


def _embedded_facts(soup: BeautifulSoup) -> dict | None:
    candidates: list[tuple[int, dict]] = []
    for script in soup.find_all("script"):
        script_type = (script.get("type") or "").casefold()
        script_id = (script.get("id") or "").casefold()
        if script_type not in {"application/json", "application/ld+json"} and script_id != "__next_data__":
            continue
        raw = script.string or script.get_text()
        if not raw or "{" not in raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        candidates.extend(_walk_embedded(payload))
    if not candidates or max(score for score, _mapped in candidates) == 0:
        return None
    merged: dict = {}
    for _score, mapped in sorted(candidates, key=lambda item: item[0], reverse=True):
        for field, value in mapped.items():
            if field not in merged or merged[field] in (None, "", []):
                merged[field] = value
    return merged


def _walk_embedded(node) -> list[tuple[int, dict]]:
    found: list[tuple[int, dict]] = []

    def visit(value, skipped: bool = False) -> None:
        if isinstance(value, dict):
            if not skipped:
                mapped = _map_embedded_dict(value)
                if mapped:
                    score = sum(1 for field in _CORE_EMBEDDED if mapped.get(field))
                    found.append((score, mapped))
            for key, child in value.items():
                child_skipped = skipped or _embedded_key(str(key)) in _SKIP_EMBEDDED_SUBTREES
                visit(child, child_skipped)
        elif isinstance(value, list) and not skipped:
            for child in value:
                visit(child, False)

    visit(node)
    return found


def _map_embedded_dict(payload: dict) -> dict:
    mapped: dict = {}
    for key, raw in payload.items():
        field = _EMBEDDED_FIELDS.get(_embedded_key(str(key)))
        if field is None or field in mapped:
            continue
        if field == "holdings":
            holdings = _normalize_holdings(raw)
            if holdings:
                mapped[field] = holdings
            continue
        if field == "nav_value" and isinstance(raw, dict):
            value = _scalar_embedded(raw.get("value") or raw.get("display") or raw.get("text"))
            if value:
                mapped["nav_value"] = value
            date = _find_date(str(raw.get("date") or raw.get("navDate") or raw.get("asOf") or ""))
            if date:
                mapped["nav_date"] = date
            continue
        if field == "category" and isinstance(raw, list):
            names = [_clean_text(str(item)) for item in raw]
            names = [name for name in names if name]
            if names:
                mapped[field] = " - ".join(names)
            continue
        value = _scalar_embedded(raw)
        if value:
            if field == "nav_date":
                mapped[field] = _find_date(value) or value
            elif field == "riskometer":
                mapped[field] = re.sub(r"\s+risk$", "", value, flags=re.I).strip()
            else:
                mapped[field] = value
    sub_category = _scalar_embedded(payload.get("sub_category") or payload.get("subCategory"))
    category = mapped.get("category")
    if sub_category and category and sub_category.casefold() not in category.casefold():
        mapped["category"] = f"{category} - {sub_category}"
    managers = _current_manager_names(payload.get("fund_manager_details") or payload.get("fundManagerDetails"))
    if managers:
        mapped["fund_manager"] = _fund_manager_sentence(managers)
    return mapped


def _current_manager_names(details) -> list[str]:
    if not isinstance(details, list):
        return []
    names: list[str] = []
    for item in details:
        if not isinstance(item, dict):
            continue
        end = item.get("date_to") or item.get("dateTo") or item.get("to_date") or item.get("end_date")
        end_text = _clean_text(str(end)) if end is not None else None
        if end_text and end_text.casefold() not in {"present", "- present"}:
            continue
        name = _scalar_embedded(item.get("person_name") or item.get("personName") or item.get("name"))
        if name and name not in names:
            names.append(name)
    return names


def _fund_manager_sentence(names: list[str]) -> str:
    if len(names) == 1:
        return f"{names[0]} is the current fund manager."
    if len(names) == 2:
        return f"{names[0]} and {names[1]} are the current fund managers."
    return f"{', '.join(names[:-1])}, and {names[-1]} are the current fund managers."


def _scalar_embedded(raw) -> str | None:
    if isinstance(raw, dict):
        for key in ("value", "display", "text", "label"):
            if key in raw:
                return _scalar_embedded(raw[key])
        return None
    if isinstance(raw, (list, tuple)) or raw is None:
        return None
    return _clean_text(str(raw))


def _normalize_holdings(raw) -> list[dict]:
    if not isinstance(raw, list):
        return []
    holdings = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = _scalar_embedded(
            item.get("name")
            or item.get("company_name")
            or item.get("companyName")
            or item.get("stock")
            or item.get("company")
        )
        if not name:
            continue
        sector = _scalar_embedded(item.get("sector") or item.get("sector_name") or item.get("sectorName")) or ""
        weight = _present_weight(
            _scalar_embedded(
                item.get("weight")
                or item.get("corpus_per")
                or item.get("corpusPer")
                or item.get("assets")
                or item.get("percentage")
                or item.get("allocation")
            )
        )
        holdings.append({"name": name, "sector": sector, "weight": weight or ""})
        if len(holdings) >= HOLDINGS_CAP:
            break
    return holdings


def _embedded_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.casefold())


def _manifest_entry(source: dict) -> dict:
    return {
        "url": source.get("url"),
        "scheme_id": source.get("scheme_id") or "",
        "document_type": source.get("document_type"),
        "authority": source.get("authority"),
        "status": "failed",
        "error": None,
    }


def _load_previous(facts_path: Path) -> dict[str, dict]:
    if not facts_path.is_file():
        return {}
    try:
        records = load_facts(facts_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    previous: dict[str, dict] = {}
    for record in records:
        url = record.get("source_url")
        if isinstance(url, str) and url:
            previous[url] = record
    return previous


def _load_previous_passages(path: Path) -> dict[str, list[dict]]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = payload.get("passages") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {}
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = row.get("source_url")
        if isinstance(url, str) and url:
            grouped.setdefault(url, []).append(row)
    return grouped


def _keep_previous_passages(passages: list[dict], previous: dict[str, list[dict]], url: str) -> None:
    passages.extend(previous.get(url, []))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _short_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    message = str(exc).strip() or exc.__class__.__name__
    return message[:200]


if __name__ == "__main__":
    raise SystemExit(main())
