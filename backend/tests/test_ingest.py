import hashlib
import json
from pathlib import Path

import httpx
import pytest

from app.services.registry import REQUIRED_GROWW_URLS, SCHEMES
from scripts.ingest import (
    USER_AGENT,
    IngestError,
    default_client_factory,
    load_sources,
    parse_scheme_html,
    run_ingest,
    validate_sources,
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SOURCES = DATA_DIR / "sources.yaml"
FIXTURES = DATA_DIR / "fixtures"
MID_CAP_URL = "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"
SMALL_CAP_URL = "https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth"


def test_sources_yaml_contains_the_required_groww_urls():
    sources = load_sources(SOURCES)
    by_url = {source["url"]: source for source in sources}
    assert set(REQUIRED_GROWW_URLS) <= set(by_url)
    assert len(REQUIRED_GROWW_URLS) == 5
    for scheme in SCHEMES:
        entry = by_url[scheme.url]
        assert entry["scheme_id"] == scheme.scheme_id
        assert entry["document_type"] == "scheme_page"
        assert entry["authority"] == "platform"
    validate_sources(sources)


def test_missing_required_url_stops_before_fetch(tmp_path):
    sources_path = tmp_path / "sources.yaml"
    _write_sources(sources_path, skip={"hdfc-silver-etf-fof"})
    opened = {"yes": False}

    def factory():
        opened["yes"] = True
        raise AssertionError("catalog validation must finish before any fetch")

    with pytest.raises(IngestError, match="hdfc-silver-etf-fof-direct-growth"):
        run_ingest(
            "live",
            sources_path=sources_path,
            facts_path=tmp_path / "scheme_facts.json",
            manifest_path=tmp_path / "manifest.json",
            client_factory=factory,
        )
    assert opened["yes"] is False
    assert not (tmp_path / "scheme_facts.json").exists()


def test_disallowed_host_stops_before_fetch(tmp_path):
    sources_path = tmp_path / "sources.yaml"
    _write_sources(
        sources_path,
        extra="""  - scheme_id: ""
    url: "https://example.com/not-allowed"
    document_type: help
    authority: platform
""",
    )
    opened = {"yes": False}

    def factory():
        opened["yes"] = True
        raise AssertionError("catalog validation must finish before any fetch")

    with pytest.raises(IngestError, match="example.com"):
        run_ingest(
            "live",
            sources_path=sources_path,
            facts_path=tmp_path / "scheme_facts.json",
            manifest_path=tmp_path / "manifest.json",
            client_factory=factory,
        )
    assert opened["yes"] is False


def test_fixture_ingest_stores_labeled_aum_and_ignores_about_and_returns(tmp_path):
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
    schemes = {record["scheme_id"]: record for record in result["schemes"]}
    mid_cap = schemes["hdfc-mid-cap"]
    assert mid_cap["aum"] == "₹45,231.18 Cr"
    assert mid_cap["expense_ratio"] == "0.74%"
    assert mid_cap["exit_load"] == "1% if redeemed within 1 year"
    assert mid_cap["minimum_sip"] == "₹100"
    assert mid_cap["minimum_lumpsum"] == "₹100"
    assert mid_cap["minimum_additional"] is None
    assert mid_cap["nav_value"] == "₹185.42"
    assert mid_cap["nav_date"] == "2026-10-30"
    assert mid_cap["riskometer"] == "Very High"
    assert mid_cap["benchmark"] == "NIFTY Midcap 150 TRI"
    assert mid_cap["category"] == "Equity - Mid Cap"
    assert mid_cap["name"] == "HDFC Mid Cap Fund Direct Growth"
    assert mid_cap["source_url"] == MID_CAP_URL
    assert mid_cap["authority"] == "platform"
    assert mid_cap["accessed_at"] == "2026-10-31"
    assert len(mid_cap["holdings"]) == 3
    assert len(mid_cap["holdings"]) <= 10
    facts_blob = json.dumps(result["schemes"])
    assert "₹12,000 Cr" not in facts_blob
    assert "12,000" not in facts_blob
    assert "18.41%" not in facts_blob
    assert "22.17%" not in facts_blob
    assert "₹9,87,654" not in facts_blob
    assert "mid-cap companies" not in facts_blob
    assert "returns" not in mid_cap
    statuses = {entry["url"]: entry["status"] for entry in result["manifest"]["sources"]}
    assert statuses[MID_CAP_URL] == "ok"
    assert statuses[SMALL_CAP_URL] == "failed"


def test_missing_exit_load_stays_null():
    record = parse_scheme_html(
        '<div class="fact-row"><span class="label">Expense ratio</span><span class="value">0.20%</span></div>',
        scheme_id="hdfc-silver-etf-fof",
        source_url="https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth",
        authority="platform",
        accessed_at="2026-10-31",
    )
    assert record["exit_load"] is None
    assert "redeemed" not in json.dumps(record).casefold()


def test_labeled_exit_load_is_stored_as_written():
    record = parse_scheme_html(
        "<table><tr><td>Exit load</td><td>Nil</td></tr></table>",
        scheme_id="hdfc-silver-etf-fof",
        source_url="https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth",
        authority="platform",
        accessed_at="2026-10-31",
    )
    assert record["exit_load"] == "Nil"


def test_holdings_are_capped_at_ten():
    rows = "\n".join(
        f"<tr><td>Company {index}</td><td>Sector</td><td>{index}.00%</td></tr>" for index in range(1, 13)
    )
    html = f"""
    <h2>Holdings</h2>
    <table>
      <tr><th>Name</th><th>Sector</th><th>Weight</th></tr>
      {rows}
    </table>
    """
    record = parse_scheme_html(
        html,
        scheme_id="hdfc-mid-cap",
        source_url=MID_CAP_URL,
        authority="platform",
        accessed_at="2026-10-31",
    )
    assert [row["name"] for row in record["holdings"]] == [f"Company {index}" for index in range(1, 11)]


def test_embedded_page_data_wins_and_skips_about_and_returns():
    html = """
    <script id="__NEXT_DATA__" type="application/json">
    {
      "props": {
        "pageProps": {
          "scheme": {
            "expenseRatio": "0.55%",
            "fundSize": "₹1,000 Cr",
            "about": {"aum": "₹12,000 Cr", "text": "The fund size is ₹12,000 Cr"},
            "returns": {"expenseRatio": "9.99%", "oneYear": "18.41%"}
          }
        }
      }
    }
    </script>
    <div class="fact-row"><span class="label">Expense ratio</span><span class="value">0.74%</span></div>
    """
    record = parse_scheme_html(
        html,
        scheme_id="hdfc-mid-cap",
        source_url=MID_CAP_URL,
        authority="platform",
        accessed_at="2026-10-31",
    )
    assert record["expense_ratio"] == "0.55%"
    assert record["aum"] == "₹1,000 Cr"
    blob = json.dumps(record)
    assert "12,000" not in blob
    assert "9.99%" not in blob
    assert "18.41%" not in blob
    assert "0.74%" not in blob


def test_groww_embedded_fields_use_the_labeled_display():
    html = """
    <script id="__NEXT_DATA__" type="application/json">
    {
      "scheme": {
        "category": "Equity",
        "sub_category": "Small Cap",
        "expense_ratio": "0.8",
        "aum": 40800.81,
        "nav": 148.615,
        "nav_date": "30-Oct-2026",
        "min_sip_investment": 100,
        "min_investment_amount": 100,
        "mini_additional_investment": 100,
        "exit_load": "Exit load of 1% if redeemed within 1 year",
        "benchmark": "BSE 250 SmallCap TRI",
        "fund_manager": "Chirag Setalvad",
        "fund_manager_details": [
          {"person_name": "Dhruv Muchhal", "date_from": "2023-06-21"},
          {"person_name": "Chirag Setalvad", "date_from": "2014-06-27"}
        ],
        "stamp_duty": "0.005% (from July 1st, 2020)",
        "holdings": [
          {"company_name": "Repo", "sector_name": "Unspecified", "corpus_per": 10.03}
        ],
        "about": {"aum": "₹9,34,076 Cr"},
        "returns": {"oneYear": "18.41%"}
      }
    }
    </script>
    """
    record = parse_scheme_html(
        html,
        scheme_id="hdfc-small-cap",
        source_url=SMALL_CAP_URL,
        authority="platform",
        accessed_at="2026-10-31",
    )
    assert record["category"] == "Equity - Small Cap"
    assert record["expense_ratio"] == "0.80%"
    assert record["aum"] == "₹40,800.81 Cr"
    assert record["nav_value"] == "₹148.62"
    assert record["nav_date"] == "2026-10-30"
    assert record["minimum_sip"] == "₹100"
    assert record["minimum_lumpsum"] == "₹100"
    assert record["minimum_additional"] == "₹100"
    assert record["fund_manager"] == "Dhruv Muchhal and Chirag Setalvad are the current fund managers."
    assert record["holdings"] == [{"name": "Repo", "sector": "Unspecified", "weight": "10.03%"}]
    blob = json.dumps(record)
    assert "9,34,076" not in blob
    assert "18.41%" not in blob


def test_failed_live_fetch_keeps_previous_record_and_paces_requests(tmp_path):
    sources_path = tmp_path / "sources.yaml"
    _write_sources(sources_path)
    previous_path = tmp_path / "scheme_facts.json"
    previous_path.write_text(
        json.dumps(
            {
                "schemes": [
                    {
                        "scheme_id": "hdfc-small-cap",
                        "name": "HDFC Small Cap Fund Direct Growth",
                        "expense_ratio": "KEEP-ME",
                        "source_url": SMALL_CAP_URL,
                        "authority": "platform",
                        "accessed_at": "2026-01-01",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    page = '<div class="fact-row"><span class="label">Expense ratio</span><span class="value">0.10%</span></div>'
    calls: list[str] = []

    class FakeResponse:
        def __init__(self, url: str):
            self.text = page
            self.content = page.encode("utf-8")
            self.url = url
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
            assert headers["User-Agent"] == USER_AGENT
            if url == SMALL_CAP_URL:
                raise httpx.ConnectError("down")
            if url == MID_CAP_URL:
                self.redirect = FakeResponse("https://evil.example/login")
                return self.redirect
            return FakeResponse(url)

    clock = {"now": 0.0}
    slept: list[float] = []

    def monotonic():
        return clock["now"]

    def sleep(seconds):
        slept.append(seconds)
        clock["now"] += seconds

    raw_dir = tmp_path / "raw"
    result = run_ingest(
        "live",
        sources_path=sources_path,
        facts_path=previous_path,
        manifest_path=tmp_path / "manifest.json",
        raw_dir=raw_dir,
        accessed_at="2026-10-31",
        sleep=sleep,
        monotonic=monotonic,
        client_factory=FakeClient,
    )
    schemes = {record["scheme_id"]: record for record in result["schemes"]}
    assert schemes["hdfc-small-cap"]["expense_ratio"] == "KEEP-ME"
    assert schemes["hdfc-small-cap"]["accessed_at"] == "2026-01-01"
    assert "hdfc-mid-cap" not in schemes
    assert schemes["hdfc-large-cap"]["expense_ratio"] == "0.10%"
    by_url = {entry["url"]: entry for entry in result["manifest"]["sources"]}
    assert by_url[SMALL_CAP_URL]["status"] == "failed"
    assert "down" in by_url[SMALL_CAP_URL]["error"]
    assert by_url[MID_CAP_URL]["status"] == "failed"
    assert "evil.example" in by_url[MID_CAP_URL]["error"]
    assert slept == [1.0, 1.0, 1.0, 1.0]
    assert calls == [scheme.url for scheme in SCHEMES]
    stored = hashlib.sha256(
        "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth".encode("utf-8")
    ).hexdigest()
    assert (raw_dir / stored).read_text(encoding="utf-8") == page
    assert not (raw_dir / hashlib.sha256(SMALL_CAP_URL.encode("utf-8")).hexdigest()).exists()
    assert not (raw_dir / hashlib.sha256(MID_CAP_URL.encode("utf-8")).hexdigest()).exists()


def test_live_client_uses_a_twenty_second_timeout_and_descriptive_user_agent():
    client = default_client_factory()
    try:
        assert client.timeout.connect == 20.0
        assert client.timeout.read == 20.0
        assert client.headers["user-agent"] == USER_AGENT
    finally:
        client.close()


def _write_sources(path: Path, skip: set[str] | None = None, extra: str = "") -> None:
    lines = ["sources:"]
    skipped = skip or set()
    for scheme in SCHEMES:
        if scheme.scheme_id in skipped:
            continue
        lines.extend(
            [
                f"  - scheme_id: {scheme.scheme_id}",
                f'    url: "{scheme.url}"',
                "    document_type: scheme_page",
                "    authority: platform",
            ]
        )
    if extra:
        lines.append(extra.rstrip("\n"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
