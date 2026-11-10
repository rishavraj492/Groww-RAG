import hashlib
import json
from pathlib import Path

import httpx

from app.services.passages import (
    TOKEN_HARD_LIMIT,
    TOKEN_SPLIT_AT,
    chunk_scheme_html,
    estimate_tokens,
    split_passage,
)
from app.services.registry import REQUIRED_GROWW_URLS, SCHEMES
from scripts.ingest import run_ingest

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SOURCES = DATA_DIR / "sources.yaml"
FIXTURES = DATA_DIR / "fixtures"
RAW = DATA_DIR / "raw"
MID_CAP_URL = "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"
SMALL_CAP_URL = "https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth"

OBJECTIVE = (
    "To generate long-term capital appreciation from a portfolio invested "
    "predominantly in equity and equity related securities of mid-cap companies."
)


def test_fixture_chunks_one_passage_per_field_and_skips_excluded_sections(tmp_path):
    result = run_ingest(
        "fixture",
        sources_path=SOURCES,
        facts_path=tmp_path / "scheme_facts.json",
        manifest_path=tmp_path / "manifest.json",
        fixtures_dir=FIXTURES,
        accessed_at="2026-10-31",
        client_factory=_reject_network,
    )
    passages = result["passages"]
    assert passages
    assert {row["scheme_id"] for row in passages} == {"hdfc-mid-cap"}
    by_topic = {}
    for row in passages:
        by_topic.setdefault(row["topic"], []).append(row)
        assert set(row) == {
            "text",
            "source_url",
            "title",
            "authority",
            "document_type",
            "scheme_id",
            "topic",
            "accessed_at",
            "as_of",
        }
        assert row["source_url"] == MID_CAP_URL
        assert row["title"] == "HDFC Mid Cap Fund Direct Growth"
        assert row["authority"] == "platform"
        assert row["document_type"] == "scheme_page"
        assert row["accessed_at"] == "2026-10-31"
        assert row["as_of"] == "2026-10-30"
        assert row["scheme_id"] in {scheme.scheme_id for scheme in SCHEMES}
        assert estimate_tokens(row["text"]) <= TOKEN_SPLIT_AT

    objective = by_topic["objective"]
    assert len(objective) == 1
    assert objective[0]["text"] == f"Investment objective: {OBJECTIVE}"
    assert len(by_topic["tax_note"]) == 1
    assert by_topic["tax_note"][0]["text"].startswith("Tax implication: ")
    assert "capital gains rules" in by_topic["tax_note"][0]["text"]
    assert len(by_topic["stamp_duty"]) == 1
    assert by_topic["stamp_duty"][0]["text"] == (
        "Stamp duty of 0.005% is applicable on purchase of mutual fund units."
    )
    assert len(by_topic["fund_manager"]) == 1
    assert by_topic["fund_manager"][0]["text"] == (
        "Fund manager: Chirag Setalvad is the current fund manager."
    )
    assert "0.74%" not in objective[0]["text"]
    assert "capital gains" not in objective[0]["text"]

    blob = json.dumps(passages)
    assert "₹12,000 Cr" not in blob
    assert "18.41%" not in blob
    assert "22.17%" not in blob
    assert "₹9,87,654" not in blob
    assert "Persistent Systems" not in blob
    assert "1% if redeemed within 1 year" not in blob
    assert "Contra funds" not in blob
    written = json.loads((tmp_path / "passages.json").read_text(encoding="utf-8"))
    assert written["passages"] == passages


def test_live_page_chunks_server_fields_and_drops_contra_returns_and_other_schemes():
    html = """
    <script id="__NEXT_DATA__" type="application/json">
    {
      "props": {"pageProps": {"mfServerSideData": {
        "description": "The scheme is seek to capital appreciation by investing in units of HDFC Silver ETF (HSETF).",
        "meta_desc": "Three year return of 9.46. Risk-reward rating of 3/10.",
        "exit_load": "Exit load of 1%, if redeemed within 15 days.",
        "stamp_duty": "0.005% (from July 1st, 2020)",
        "category_info": {
          "description": "Contra funds follow Contrarian strategy which means investing in stocks in contrast to the prevailing sentiment.",
          "category_helper_text": "Invests in stocks as per Contrarian investment strategy",
          "definition": "A contra category definition that must not be indexed.",
          "tax_impact": "If you redeem within two years, returns are taxed as per your Income Tax slab."
        },
        "amc_info": {"description": "Its managing total assets of ₹2,70,046 Cr as of 30th Sep 2017."},
        "analysis": [{"analysis_desc": "Consistently lower annualised returns than category average"}],
        "holdings": [{"company_name": "Should Not Index Ltd", "corpus_per": 4.2}],
        "historic_fund_expense": [{"expense_ratio": "0.99%"}],
        "historic_exit_loads": [{"note": "Exit load of 2% if redeemed within 12 months"}],
        "peerComparison": [{"scheme_name": "Other Small Cap Fund Direct Growth"}],
        "fund_manager_details": [
          {
            "person_name": "Arun Agarwal",
            "education": "Mr. Agarwal is a CFA.",
            "experience": "Prior to joining HDFC AMC he worked at Example Capital.",
            "funds_managed": [{"scheme_name": "Other Scheme Fund Direct Growth"}]
          },
          {
            "person_name": "Nandita Menezes",
            "education": "Ms. Menezes holds an MBA.",
            "experience": "She previously worked at Example Bank.",
            "date_to": null
          },
          {
            "person_name": "Former Manager",
            "education": "A past degree.",
            "experience": "Left the fund in 2019.",
            "date_to": "2019-01-01"
          }
        ]
      }}}
    }
    </script>
    <h2>Understand terms</h2>
    <p>Annualised returns Average of the yearly returns of a mutual fund over a given period.</p>
    <h2>Return calculator</h2>
    <p>Would've become ₹9,87,654</p>
    """
    passages = chunk_scheme_html(
        html,
        scheme_id="hdfc-silver-etf-fof",
        source_url="https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth",
        title="HDFC Silver ETF FoF Direct Growth",
        authority="platform",
        document_type="scheme_page",
        accessed_at="2026-10-31",
        as_of="2026-10-30",
    )
    by_topic: dict[str, list[dict]] = {}
    for row in passages:
        by_topic.setdefault(row["topic"], []).append(row)
    assert [row["text"] for row in by_topic["objective"]] == [
        "Investment objective: The scheme is seek to capital appreciation by investing in units of HDFC Silver ETF (HSETF)."
    ]
    assert by_topic["tax_note"][0]["text"].startswith("Tax implication: If you redeem within two years")
    assert by_topic["stamp_duty"][0]["text"] == "Stamp duty: 0.005% (from July 1st, 2020)"
    managers = by_topic["fund_manager"]
    assert len(managers) == 2
    assert "Arun Agarwal" in managers[0]["text"]
    assert "Nandita Menezes" in managers[1]["text"]
    assert "Arun Agarwal" not in managers[1]["text"]
    assert "Other Scheme Fund" not in managers[0]["text"]
    blob = json.dumps(passages)
    assert "Contra funds" not in blob
    assert "Contrarian" not in blob
    assert "contra category definition" not in blob
    assert "2,70,046" not in blob
    assert "9.46" not in blob
    assert "Should Not Index" not in blob
    assert "0.99%" not in blob
    assert "within 12 months" not in blob
    assert "Other Small Cap" not in blob
    assert "Former Manager" not in blob
    assert "within 15 days" not in blob
    assert "Annualised returns" not in blob
    assert "₹9,87,654" not in blob
    assert {row["source_url"] for row in passages} <= set(REQUIRED_GROWW_URLS)


def test_saved_raw_scheme_pages_use_the_same_fields():
    expected = {
        "hdfc-small-cap": "predominantly in Small-Cap companies.",
        "hdfc-large-cap": "predominantly in Large-Cap companies.",
        "hdfc-silver-etf-fof": "The scheme is seek to capital appreciation",
        "hdfc-multi-cap": "large cap, mid cap",
    }
    found = 0
    for scheme in SCHEMES:
        path = RAW / hashlib.sha256(scheme.url.encode("utf-8")).hexdigest()
        if not path.is_file():
            continue
        found += 1
        passages = chunk_scheme_html(
            path.read_text(encoding="utf-8"),
            scheme_id=scheme.scheme_id,
            source_url=scheme.url,
            title=scheme.name,
            authority="platform",
            document_type="scheme_page",
            accessed_at="2026-10-31",
            as_of=None,
        )
        topics = {row["topic"] for row in passages}
        assert topics == {"objective", "tax_note", "stamp_duty", "fund_manager"}
        objective = next(row["text"] for row in passages if row["topic"] == "objective")
        assert expected[scheme.scheme_id] in objective
        assert len([row for row in passages if row["topic"] == "fund_manager"]) == 2
        blob = json.dumps(passages)
        assert "Contra funds" not in blob
        assert "2,70,046" not in blob
        assert all(estimate_tokens(row["text"]) <= TOKEN_SPLIT_AT for row in passages)
        assert all(row["scheme_id"] == scheme.scheme_id for row in passages)
    assert found == 4


def test_live_miss_does_not_invent_passages_from_the_fixture(tmp_path):
    sources_path = tmp_path / "sources.yaml"
    _write_sources(sources_path)

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, url, headers=None):
            if url == MID_CAP_URL:
                raise httpx.ConnectError("mid-cap raw body missing")
            return _Ok(url)

    result = run_ingest(
        "live",
        sources_path=sources_path,
        facts_path=tmp_path / "scheme_facts.json",
        manifest_path=tmp_path / "manifest.json",
        fixtures_dir=FIXTURES,
        raw_dir=tmp_path / "raw",
        accessed_at="2026-10-31",
        sleep=lambda _seconds: None,
        monotonic=lambda: 0.0,
        client_factory=FakeClient,
    )
    assert all(row["scheme_id"] != "hdfc-mid-cap" for row in result["passages"])
    assert "mid-cap companies" not in json.dumps(result["passages"])
    assert (FIXTURES / "hdfc_mid_cap.html").is_file()


def test_pdf_body_and_other_document_types_produce_no_passages():
    kwargs = dict(
        scheme_id="hdfc-mid-cap",
        source_url=MID_CAP_URL,
        title="HDFC Mid Cap Fund Direct Growth",
        authority="platform",
        accessed_at="2026-10-31",
        as_of=None,
    )
    assert chunk_scheme_html("%PDF-1.7\nstream", document_type="scheme_page", **kwargs) == []
    assert chunk_scheme_html("<h2>Investment objective</h2><p>Ignore.</p>", document_type="factsheet", **kwargs) == []
    assert (
        chunk_scheme_html(
            "<h2>Investment objective</h2><p>Ignore.</p>",
            document_type="scheme_page",
            scheme_id="not-a-scheme",
            source_url=MID_CAP_URL,
            title="Other",
            authority="platform",
            accessed_at="2026-10-31",
            as_of=None,
        )
        == []
    )


def test_long_field_splits_with_overlap_under_the_model_limit():
    words = [f"w{index}" for index in range(450)]
    pieces = split_passage("Investment objective: " + " ".join(words))
    assert len(pieces) > 1
    assert pieces[0].startswith("Investment objective:")
    assert all(estimate_tokens(piece) <= TOKEN_SPLIT_AT for piece in pieces)
    assert all(estimate_tokens(piece) <= TOKEN_HARD_LIMIT for piece in pieces)
    assert pieces[-1].split()[-1] == "w449"
    first = set(pieces[0].split())
    second = set(pieces[1].split())
    assert first & second
    short = split_passage(f"Investment objective: {OBJECTIVE}")
    assert short == [f"Investment objective: {OBJECTIVE}"]


def _reject_network():
    raise AssertionError("fixture ingest must not open an HTTP client")


class _Ok:
    def __init__(self, url: str):
        self.text = '<div class="fact-row"><span class="label">Expense ratio</span><span class="value">0.10%</span></div>'
        self.url = url
        self.status_code = 200

    def raise_for_status(self):
        return None


def _write_sources(path: Path) -> None:
    lines = ["sources:"]
    for scheme in SCHEMES:
        lines.extend(
            [
                f"  - scheme_id: {scheme.scheme_id}",
                f'    url: "{scheme.url}"',
                "    document_type: scheme_page",
                "    authority: platform",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
