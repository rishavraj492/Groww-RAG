"""Phase 6: official factsheets, merge/conflict rules, and citation preference."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.answer import render
from app.services.official import (
    extract_official_fields,
    merge_official_fields,
    normalize_fact_value,
    values_match,
)
from app.services.resolve import resolve
from scripts.ingest import load_sources, run_ingest, validate_sources

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SOURCES = DATA_DIR / "sources.yaml"
FIXTURES = DATA_DIR / "fixtures"
OFFICIAL_FIXTURES = FIXTURES / "official"
MID_GROWW = "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"
MID_OFFICIAL = "https://www.hdfcfund.com/explore/mutual-funds/hdfc-mid-cap-fund/direct"
AMFI_EXPENSE = "https://www.amfiindia.com/investor/knowledge-center-info?zoneName=expenseRatio"
SEBI_RISK = "https://investor.sebi.gov.in/riskometer.html"
AMFI_ELSS = "https://www.amfiindia.com/investor"


def test_sources_yaml_lists_official_factsheets_and_definition_pages():
    sources = load_sources(SOURCES)
    validate_sources(sources)
    by_url = {source["url"]: source for source in sources}
    assert MID_OFFICIAL in by_url
    assert by_url[MID_OFFICIAL]["document_type"] == "factsheet"
    assert by_url[MID_OFFICIAL]["authority"] == "official"
    assert by_url[MID_OFFICIAL]["scheme_id"] == "hdfc-mid-cap"
    for scheme_id in (
        "hdfc-small-cap",
        "hdfc-large-cap",
        "hdfc-silver-etf-fof",
        "hdfc-multi-cap",
    ):
        matches = [
            source
            for source in sources
            if source.get("scheme_id") == scheme_id and source.get("document_type") == "factsheet"
        ]
        assert len(matches) == 1
        assert matches[0]["authority"] == "official"
    assert by_url[AMFI_EXPENSE]["topic"] == "definition"
    assert by_url[AMFI_EXPENSE]["authority"] == "official"
    assert by_url[SEBI_RISK]["topic"] == "definition"
    assert by_url[AMFI_ELSS]["topic"] == "elss_lock_in"
    assert by_url[AMFI_ELSS]["scheme_id"] in ("", None)


def test_normalize_expense_ratio_and_rupee_forms():
    assert values_match("expense_ratio", "0.74%", "0.74")
    assert values_match("expense_ratio", "0.74%", "0.740%")
    assert values_match("expense_ratio", " 0.74% ", "0.74%")
    assert not values_match("expense_ratio", "0.74%", "0.66%")
    assert values_match("minimum_sip", "₹100", "100")
    assert not values_match("minimum_sip", "₹100", "₹200")
    assert normalize_fact_value("expense_ratio", "0.74%") == normalize_fact_value("expense_ratio", "0.740")


def test_matching_official_expense_ratio_replaces_groww_citation(tmp_path):
    sources_path = tmp_path / "sources.yaml"
    sources_path.write_text(
        f"""sources:
  - scheme_id: hdfc-mid-cap
    url: "{MID_GROWW}"
    document_type: scheme_page
    authority: platform
  - scheme_id: hdfc-mid-cap
    url: "{MID_OFFICIAL}"
    document_type: factsheet
    authority: official
    fixture: official/hdfc_mid_cap_factsheet_match.html
""",
        encoding="utf-8",
    )
    # Keep required Groww URLs so validate_sources passes.
    _append_required_groww(sources_path, skip={"hdfc-mid-cap"})

    result = run_ingest(
        "fixture",
        sources_path=sources_path,
        facts_path=tmp_path / "scheme_facts.json",
        manifest_path=tmp_path / "manifest.json",
        fixtures_dir=FIXTURES,
        accessed_at="2026-10-31",
    )
    mid = next(record for record in result["schemes"] if record["scheme_id"] == "hdfc-mid-cap")
    assert mid["expense_ratio"] == "0.74%"
    assert mid["source_url"] == MID_OFFICIAL
    assert mid["authority"] == "official"
    official_entry = next(entry for entry in result["manifest"]["sources"] if entry["url"] == MID_OFFICIAL)
    assert official_entry["status"] == "ok"
    assert official_entry.get("conflict") is not True

    answer = render(result["schemes"], resolve("What is the expense ratio of HDFC Mid Cap?"))
    assert answer.response_type == "factual"
    assert "0.74%" in answer.answer
    assert len(answer.citations) == 1
    citation = answer.citations[0]
    assert citation.url == MID_OFFICIAL
    assert citation.title == "HDFC Mid Cap Fund Direct Growth"
    assert citation.authority == "official"
    assert citation.accessed_at == "2026-10-31"
    assert citation.as_of is None
    assert MID_GROWW not in [item.url for item in answer.citations]


def test_conflicting_official_expense_ratio_speaks_official_and_keeps_platform_value(tmp_path):
    sources_path = tmp_path / "sources.yaml"
    sources_path.write_text(
        f"""sources:
  - scheme_id: hdfc-mid-cap
    url: "{MID_GROWW}"
    document_type: scheme_page
    authority: platform
  - scheme_id: hdfc-mid-cap
    url: "{MID_OFFICIAL}"
    document_type: factsheet
    authority: official
    fixture: official/hdfc_mid_cap_factsheet_conflict.html
""",
        encoding="utf-8",
    )
    _append_required_groww(sources_path, skip={"hdfc-mid-cap"})

    result = run_ingest(
        "fixture",
        sources_path=sources_path,
        facts_path=tmp_path / "scheme_facts.json",
        manifest_path=tmp_path / "manifest.json",
        fixtures_dir=FIXTURES,
        accessed_at="2026-10-31",
    )
    mid = next(record for record in result["schemes"] if record["scheme_id"] == "hdfc-mid-cap")
    assert mid["expense_ratio"] == "0.66%"
    assert mid["source_url"] == MID_OFFICIAL
    assert mid["authority"] == "official"
    official_entry = next(entry for entry in result["manifest"]["sources"] if entry["url"] == MID_OFFICIAL)
    assert official_entry["conflict"] is True
    assert official_entry["platform_value"]["expense_ratio"] == "0.74%"
    assert "0.70%" not in json.dumps(mid)  # not averaged

    answer = render(result["schemes"], resolve("What is the expense ratio of HDFC Mid Cap?"))
    assert answer.response_type == "factual"
    assert "0.66%" in answer.answer
    assert "0.74%" not in answer.answer
    assert answer.citations[0].url == MID_OFFICIAL
    assert answer.citations[0].authority == "official"


def test_definition_example_expense_ratio_does_not_overwrite_scheme_fact(tmp_path):
    sources_path = tmp_path / "sources.yaml"
    sources_path.write_text(
        f"""sources:
  - scheme_id: hdfc-mid-cap
    url: "{MID_GROWW}"
    document_type: scheme_page
    authority: platform
  - scheme_id: ""
    url: "{AMFI_EXPENSE}"
    document_type: regulatory
    authority: official
    topic: definition
    fixture: official/expense_ratio_definition.html
""",
        encoding="utf-8",
    )
    _append_required_groww(sources_path, skip={"hdfc-mid-cap"})

    result = run_ingest(
        "fixture",
        sources_path=sources_path,
        facts_path=tmp_path / "scheme_facts.json",
        manifest_path=tmp_path / "manifest.json",
        fixtures_dir=FIXTURES,
        accessed_at="2026-10-31",
    )
    mid = next(record for record in result["schemes"] if record["scheme_id"] == "hdfc-mid-cap")
    assert mid["expense_ratio"] == "0.74%"
    assert mid["authority"] == "platform"
    assert mid["source_url"] == MID_GROWW
    definition = next(entry for entry in result["manifest"]["sources"] if entry["url"] == AMFI_EXPENSE)
    assert definition["status"] == "ok"
    assert any(passage["source_url"] == AMFI_EXPENSE for passage in result["passages"])
    assert any("1%" in passage["text"] for passage in result["passages"])


def test_live_one_hop_sid_is_fetched_once_when_allowlisted(tmp_path):
    sid_url = "https://www.hdfcfund.com/mutual-funds/fund-documents/sid/hdfc-mid-cap"
    groww_html = f"""
    <div class="fact-row"><span class="label">Expense ratio</span><span class="value">0.74%</span></div>
    <a href="{sid_url}">Scheme Information Document</a>
    """
    sid_html = """
    <table>
      <tr><th>Expense ratio</th><td>0.66%</td></tr>
    </table>
    """
    sources_path = tmp_path / "sources.yaml"
    sources_path.write_text(
        f"""sources:
  - scheme_id: hdfc-mid-cap
    url: "{MID_GROWW}"
    document_type: scheme_page
    authority: platform
""",
        encoding="utf-8",
    )
    _append_required_groww(sources_path, skip={"hdfc-mid-cap"})

    calls: list[str] = []

    class FakeResponse:
        def __init__(self, url: str, body: str):
            self.url = url
            self.content = body.encode("utf-8")
            self.text = body
            self.status_code = 200

        def raise_for_status(self):
            return None

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, url, headers=None):
            calls.append(url)
            if url == MID_GROWW:
                return FakeResponse(url, groww_html)
            if url == sid_url:
                return FakeResponse(url, sid_html)
            return FakeResponse(url, '<div class="fact-row"><span class="label">Expense ratio</span><span class="value">0.10%</span></div>')

    clock = {"now": 0.0}

    result = run_ingest(
        "live",
        sources_path=sources_path,
        facts_path=tmp_path / "scheme_facts.json",
        manifest_path=tmp_path / "manifest.json",
        raw_dir=tmp_path / "raw",
        accessed_at="2026-10-31",
        sleep=lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
        monotonic=lambda: clock["now"],
        client_factory=FakeClient,
    )
    mid = next(record for record in result["schemes"] if record["scheme_id"] == "hdfc-mid-cap")
    assert mid["expense_ratio"] == "0.66%"
    assert mid["source_url"] == sid_url
    assert mid["authority"] == "official"
    assert sid_url in calls
    assert calls.count(sid_url) == 1
    sid_entry = next(entry for entry in result["manifest"]["sources"] if entry["url"] == sid_url)
    assert sid_entry["document_type"] == "sid"
    assert sid_entry["conflict"] is True
    assert sid_entry["platform_value"]["expense_ratio"] == "0.74%"
    # One hop only: nothing linked from the SID is fetched.
    assert all(not url.endswith(".pdf") for url in calls)


def test_live_skips_sid_on_disallowed_host(tmp_path):
    sid_url = "https://files.hdfcfund.com/sid/hdfc-mid-cap.pdf"
    groww_html = f"""
    <div class="fact-row"><span class="label">Expense ratio</span><span class="value">0.74%</span></div>
    <a href="{sid_url}">Scheme Information Document</a>
    """
    sources_path = tmp_path / "sources.yaml"
    sources_path.write_text(
        f"""sources:
  - scheme_id: hdfc-mid-cap
    url: "{MID_GROWW}"
    document_type: scheme_page
    authority: platform
""",
        encoding="utf-8",
    )
    _append_required_groww(sources_path, skip={"hdfc-mid-cap"})
    calls: list[str] = []

    class FakeResponse:
        def __init__(self, url: str, body: str):
            self.url = url
            self.content = body.encode("utf-8")
            self.status_code = 200

        def raise_for_status(self):
            return None

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, url, headers=None):
            calls.append(url)
            return FakeResponse(
                url,
                groww_html
                if url == MID_GROWW
                else '<div class="fact-row"><span class="label">Expense ratio</span><span class="value">0.10%</span></div>',
            )

    result = run_ingest(
        "live",
        sources_path=sources_path,
        facts_path=tmp_path / "scheme_facts.json",
        manifest_path=tmp_path / "manifest.json",
        raw_dir=tmp_path / "raw",
        accessed_at="2026-10-31",
        sleep=lambda _seconds: None,
        monotonic=lambda: 0.0,
        client_factory=FakeClient,
    )
    mid = next(record for record in result["schemes"] if record["scheme_id"] == "hdfc-mid-cap")
    assert mid["expense_ratio"] == "0.74%"
    assert mid["authority"] == "platform"
    assert sid_url not in calls


def test_merge_helper_records_conflict_without_averaging():
    platform = {
        "scheme_id": "hdfc-mid-cap",
        "name": "HDFC Mid Cap Fund Direct Growth",
        "expense_ratio": "0.74%",
        "exit_load": "1% if redeemed within 1 year",
        "source_url": MID_GROWW,
        "authority": "platform",
        "accessed_at": "2026-10-31",
    }
    merged, platform_value = merge_official_fields(
        platform,
        {"expense_ratio": "0.66%"},
        official_url=MID_OFFICIAL,
    )
    assert merged["expense_ratio"] == "0.66%"
    assert merged["exit_load"] == "1% if redeemed within 1 year"
    assert merged["authority"] == "official"
    assert merged["source_url"] == MID_OFFICIAL
    assert platform_value == {"expense_ratio": "0.74%"}
    assert extract_official_fields(
        (OFFICIAL_FIXTURES / "hdfc_mid_cap_factsheet_conflict.html").read_text(encoding="utf-8")
    )["expense_ratio"] == "0.66%"


def test_default_fixture_ingest_stays_offline_for_official_rows(tmp_path):
    """Official catalog rows without local fixtures fail offline; Groww mid-cap still loads."""

    def factory():
        raise AssertionError("fixture ingest must not open an HTTP client")

    result = run_ingest(
        "fixture",
        sources_path=SOURCES,
        facts_path=tmp_path / "scheme_facts.json",
        manifest_path=tmp_path / "manifest.json",
        fixtures_dir=FIXTURES,
        accessed_at="2026-10-31",
        client_factory=factory,
    )
    mid = next(record for record in result["schemes"] if record["scheme_id"] == "hdfc-mid-cap")
    assert mid["expense_ratio"] == "0.74%"
    assert mid["authority"] == "platform"
    assert mid["source_url"] == MID_GROWW
    official = next(entry for entry in result["manifest"]["sources"] if entry["url"] == MID_OFFICIAL)
    assert official["status"] == "failed"


def _append_required_groww(path: Path, skip: set[str]) -> None:
    from app.services.registry import SCHEMES

    lines = [path.read_text(encoding="utf-8").rstrip(), ""]
    for scheme in SCHEMES:
        if scheme.scheme_id in skip:
            continue
        lines.extend(
            [
                f"  - scheme_id: {scheme.scheme_id}",
                f'    url: "{scheme.url}"',
                "    document_type: scheme_page",
                "    authority: platform",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
