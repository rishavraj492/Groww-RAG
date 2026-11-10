from pathlib import Path

import pytest

from app.config import EDUCATION_URLS, HOLDINGS_CAP
from app.services.answer import Citation, render, render_refusal
from app.services.classify import classify
from app.services.facts import load_facts
from app.services.resolve import resolve

FIXTURE_FACTS = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "scheme_facts.json"
MID_URL = "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"
SMALL_URL = "https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth"
LARGE_URL = "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth"
OFFICIAL_URL = "https://www.hdfcfund.com/docs/hdfc-mid-cap-factsheet"
UNAVAILABLE = (
    "I don’t have that in the sources for this assistant. "
    "Check the scheme page on Groww or the HDFC Mutual Fund documents for this scheme."
)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (
            "What is the expense ratio of HDFC Mid Cap?",
            "The expense ratio of HDFC Mid Cap Fund Direct Growth is 0.74%. "
            "Last updated from sources: 2026-10-31.",
        ),
        (
            "What is the exit load of HDFC Mid Cap?",
            "The exit load of HDFC Mid Cap Fund Direct Growth is 1% if redeemed within 1 year. "
            "Last updated from sources: 2026-10-31.",
        ),
        (
            "What is the minimum SIP of HDFC Mid Cap?",
            "The minimum SIP of HDFC Mid Cap Fund Direct Growth is ₹100. "
            "Last updated from sources: 2026-10-31.",
        ),
        (
            "What is the riskometer of HDFC Mid Cap?",
            "The riskometer of HDFC Mid Cap Fund Direct Growth is Very High. "
            "Last updated from sources: 2026-10-31.",
        ),
        (
            "What is the benchmark of HDFC Mid Cap?",
            "The benchmark of HDFC Mid Cap Fund Direct Growth is NIFTY Midcap 150 TRI. "
            "Last updated from sources: 2026-10-31.",
        ),
    ],
)
def test_labeled_facts_use_the_fixture_sentence_and_groww_url(question, expected):
    result = render(load_facts(FIXTURE_FACTS), resolve(question))
    assert result.response_type == "factual"
    assert result.answer == expected
    assert result.scheme_ids == ("hdfc-mid-cap",)
    assert result.citations == (
        Citation(
            url=MID_URL,
            title="HDFC Mid Cap Fund Direct Growth",
            authority="platform",
            accessed_at="2026-10-31",
            as_of=None,
        ),
    )
    lowered = result.answer.lower()
    assert "better" not in lowered
    assert "recommend" not in lowered
    assert "should" not in lowered


def test_null_expense_ratio_is_unavailable_with_the_groww_url():
    result = render(load_facts(FIXTURE_FACTS), resolve("What is the expense ratio of HDFC Small Cap?"))
    assert result.response_type == "unavailable"
    assert result.answer == UNAVAILABLE
    assert result.scheme_ids == ("hdfc-small-cap",)
    assert result.citations == (
        Citation(
            url=SMALL_URL,
            title="HDFC Small Cap Fund Direct Growth",
            authority="platform",
            accessed_at="2026-10-31",
            as_of=None,
        ),
    )
    assert not any(char.isdigit() for char in result.answer)


def test_missing_scheme_record_points_at_groww_without_a_number():
    result = render(load_facts(FIXTURE_FACTS), resolve("What is the exit load of HDFC Large Cap?"))
    assert result.response_type == "unavailable"
    assert result.answer == UNAVAILABLE
    assert result.citations[0].url == LARGE_URL
    assert result.citations[0].accessed_at is None
    assert not any(char.isdigit() for char in result.answer)


def test_two_schemes_produce_two_sentences_and_no_comparison():
    result = render(load_facts(FIXTURE_FACTS), resolve("Mid cap and small cap exit load"))
    assert result.response_type == "factual"
    assert result.answer == (
        "The exit load of HDFC Mid Cap Fund Direct Growth is 1% if redeemed within 1 year. "
        "The exit load of HDFC Small Cap Fund Direct Growth is 1% if redeemed within 1 year. "
        "Last updated from sources: 2026-10-31."
    )
    assert result.scheme_ids == ("hdfc-mid-cap", "hdfc-small-cap")
    assert [item.url for item in result.citations] == [MID_URL, SMALL_URL]
    lowered = result.answer.lower()
    assert "better" not in lowered
    assert "recommend" not in lowered
    assert "should" not in lowered


def test_two_schemes_do_not_invent_a_null_expense_ratio():
    result = render(load_facts(FIXTURE_FACTS), resolve("Mid cap and small cap expense ratio"))
    assert result.response_type == "factual"
    assert result.answer == (
        "The expense ratio of HDFC Mid Cap Fund Direct Growth is 0.74%. "
        "The expense ratio of HDFC Small Cap Fund Direct Growth is not in the sources for this assistant. "
        "Last updated from sources: 2026-10-31."
    )
    assert result.answer.count("%") == 1
    assert [item.url for item in result.citations] == [MID_URL, SMALL_URL]
    assert "better" not in result.answer.lower()


def test_different_capture_dates_are_stated_per_scheme():
    facts = [
        {
            "scheme_id": "hdfc-mid-cap",
            "name": "HDFC Mid Cap Fund Direct Growth",
            "exit_load": "1%",
            "source_url": MID_URL,
            "authority": "platform",
            "accessed_at": "2026-10-31",
        },
        {
            "scheme_id": "hdfc-small-cap",
            "name": "HDFC Small Cap Fund Direct Growth",
            "exit_load": "2%",
            "source_url": SMALL_URL,
            "authority": "platform",
            "accessed_at": "2026-10-01",
        },
    ]
    result = render(facts, resolve("Mid cap and small cap exit load"))
    assert result.answer == (
        "The exit load of HDFC Mid Cap Fund Direct Growth is 1%. "
        "Last updated from sources: 2026-10-31. "
        "The exit load of HDFC Small Cap Fund Direct Growth is 2%. "
        "Last updated from sources: 2026-10-01."
    )


def test_official_authority_cites_the_official_url():
    facts = [
        {
            "scheme_id": "hdfc-mid-cap",
            "name": "HDFC Mid Cap Fund Direct Growth",
            "expense_ratio": "0.66%",
            "source_url": OFFICIAL_URL,
            "authority": "official",
            "accessed_at": "2026-10-31",
        }
    ]
    result = render(facts, resolve("What is the expense ratio of HDFC Mid Cap?"))
    assert result.answer == (
        "The expense ratio of HDFC Mid Cap Fund Direct Growth is 0.66%. "
        "Last updated from sources: 2026-10-31."
    )
    assert result.citations[0].url == OFFICIAL_URL
    assert result.citations[0].authority == "official"
    assert MID_URL not in [item.url for item in result.citations]
    assert "0.74%" not in result.answer


def test_null_field_on_an_official_record_still_cites_groww():
    facts = [
        {
            "scheme_id": "hdfc-mid-cap",
            "name": "HDFC Mid Cap Fund Direct Growth",
            "expense_ratio": None,
            "source_url": OFFICIAL_URL,
            "authority": "official",
            "accessed_at": "2026-10-31",
        }
    ]
    result = render(facts, resolve("expense ratio of mid cap"))
    assert result.response_type == "unavailable"
    assert result.citations[0].url == MID_URL
    assert result.citations[0].authority == "platform"


def test_platform_citation_uses_the_registry_groww_url():
    facts = [
        {
            "scheme_id": "hdfc-mid-cap",
            "name": "HDFC Mid Cap Fund Direct Growth",
            "expense_ratio": "0.74%",
            "source_url": MID_URL + "?extra=1",
            "authority": "platform",
            "accessed_at": "2026-10-31",
        }
    ]
    result = render(facts, resolve("expense ratio of mid cap"))
    assert result.citations[0].url == MID_URL


def test_nav_reply_includes_the_nav_date():
    result = render(load_facts(FIXTURE_FACTS), resolve("What is the NAV of HDFC Mid Cap?"))
    assert result.answer == (
        "The NAV of HDFC Mid Cap Fund Direct Growth is ₹185.42 as of 2026-10-30. "
        "Last updated from sources: 2026-10-31."
    )
    assert result.citations[0].as_of == "2026-10-30"
    assert result.citations[0].url == MID_URL


def test_fund_manager_uses_the_captured_sentence():
    result = render(load_facts(FIXTURE_FACTS), resolve("Who is the fund manager of HDFC Small Cap?"))
    assert result.answer == (
        "The current fund manager is Roshi Jain. Last updated from sources: 2026-10-31."
    )
    assert result.citations[0].url == SMALL_URL


def test_tax_note_keeps_the_page_description():
    result = render(load_facts(FIXTURE_FACTS), resolve("What tax note does the mid-cap page state?"))
    assert result.answer == (
        "Equity mutual funds are taxed as per prevailing capital gains rules. "
        "This is the page's general description. Last updated from sources: 2026-10-31."
    )
    assert result.answer.lower().count("general description") == 1
    assert result.citations[0].url == MID_URL


def test_tax_note_adds_the_general_description_when_the_page_omits_it():
    facts = [
        {
            "scheme_id": "hdfc-mid-cap",
            "name": "HDFC Mid Cap Fund Direct Growth",
            "tax_note": "Equity funds follow the page tax rules.",
            "source_url": MID_URL,
            "authority": "platform",
            "accessed_at": "2026-10-31",
        }
    ]
    result = render(facts, resolve("What tax note does the mid cap page state?"))
    assert "This is the page's general description." in result.answer
    assert result.answer.startswith("Equity funds follow the page tax rules.")


def test_scheme_lock_in_states_category_and_exit_load():
    facts = [
        {
            "scheme_id": "hdfc-large-cap",
            "name": "HDFC Large Cap Fund Direct Growth",
            "category": "Equity - Large Cap",
            "exit_load": "1% if redeemed within 1 year",
            "source_url": LARGE_URL,
            "authority": "platform",
            "accessed_at": "2026-10-31",
        }
    ]
    result = render(facts, resolve("ELSS lock-in of HDFC Large Cap"))
    assert result.response_type == "factual"
    assert result.answer == (
        "HDFC Large Cap Fund Direct Growth is in the Equity - Large Cap category. "
        "The exit load of HDFC Large Cap Fund Direct Growth is 1% if redeemed within 1 year. "
        "Last updated from sources: 2026-10-31."
    )
    assert result.citations[0].url == LARGE_URL
    lowered = result.answer.lower()
    assert "elss" not in lowered
    assert "three-year" not in lowered
    assert "three year" not in lowered
    assert "3-year" not in lowered
    assert "3 years" not in lowered


def test_general_elss_question_does_not_invent_a_lock_in():
    result = render(load_facts(FIXTURE_FACTS), resolve("What is the ELSS lock-in?"))
    assert result.response_type == "unavailable"
    assert result.answer == UNAVAILABLE
    assert result.scheme_ids == ()
    assert result.citations == ()
    assert "three" not in result.answer.lower()
    assert not any(char.isdigit() for char in result.answer)


def test_definition_is_not_filled_from_a_scheme_field():
    result = render(load_facts(FIXTURE_FACTS), resolve("What is a riskometer?"))
    assert result.response_type == "unavailable"
    assert result.answer == UNAVAILABLE
    assert "Very High" not in result.answer
    assert result.citations == ()


def test_statement_download_is_not_answered_from_scheme_facts():
    result = render(load_facts(FIXTURE_FACTS), resolve("How do I download a capital gains statement?"))
    assert result.response_type == "unavailable"
    assert result.citations == ()
    assert "0.74%" not in result.answer


def test_ambiguous_schemes_do_not_produce_a_number():
    result = render(
        load_facts(FIXTURE_FACTS),
        resolve("expense ratio of mid cap, small cap, and large cap"),
    )
    assert result.response_type == "unavailable"
    assert "0.74%" not in result.answer
    assert result.citations == ()


def test_holdings_list_the_captured_rows():
    result = render(load_facts(FIXTURE_FACTS), resolve("What are the holdings of HDFC Mid Cap?"))
    assert result.answer == (
        "The holdings of HDFC Mid Cap Fund Direct Growth are "
        "Persistent Systems Ltd (Technology, 4.20%); "
        "Max Healthcare Institute Ltd (Healthcare, 3.10%). "
        "Last updated from sources: 2026-10-31."
    )
    assert result.citations[0].url == MID_URL


def test_holdings_are_capped():
    rows = [
        {"name": f"Holding {index:02d}", "sector": "Sector", "weight": f"{index}.00%"}
        for index in range(1, HOLDINGS_CAP + 3)
    ]
    facts = [
        {
            "scheme_id": "hdfc-mid-cap",
            "name": "HDFC Mid Cap Fund Direct Growth",
            "holdings": rows,
            "source_url": MID_URL,
            "authority": "platform",
            "accessed_at": "2026-10-31",
        }
    ]
    result = render(facts, resolve("holdings of mid cap"))
    assert "Holding 10" in result.answer
    assert "10.00%" in result.answer
    assert "Holding 11" not in result.answer
    assert "Holding 12" not in result.answer
    assert "11.00%" not in result.answer
    assert result.answer.count("Holding") == HOLDINGS_CAP


def test_prior_scheme_answers_the_follow_up_field():
    result = render(
        load_facts(FIXTURE_FACTS),
        resolve("and the exit load?", prior_scheme_id="hdfc-mid-cap"),
    )
    assert result.answer == (
        "The exit load of HDFC Mid Cap Fund Direct Growth is 1% if redeemed within 1 year. "
        "Last updated from sources: 2026-10-31."
    )
    assert result.citations[0].url == MID_URL


def test_named_scheme_wins_over_prior_scheme():
    result = render(
        load_facts(FIXTURE_FACTS),
        resolve("What is the exit load of small cap?", prior_scheme_id="hdfc-mid-cap"),
    )
    assert "HDFC Small Cap Fund Direct Growth" in result.answer
    assert "HDFC Mid Cap Fund Direct Growth" not in result.answer
    assert result.citations[0].url == SMALL_URL


def test_advice_uses_the_fixed_refusal_and_education_links():
    result = render_refusal(classify("Should I invest in HDFC Mid Cap?"))
    assert result.response_type == "refusal"
    assert result.answer == (
        "I can only share factual information from public sources. "
        "I can’t recommend a scheme, compare which one is better, or predict returns. "
        "For investor education, see the AMFI investor page."
    )
    assert result.scheme_ids == ()
    assert [item.url for item in result.citations] == list(EDUCATION_URLS)
    assert "0.74%" not in result.answer


def test_personal_data_refusal_does_not_echo_the_identifier():
    secret = "ABCDE1234F"
    result = render_refusal(classify(f"My PAN is {secret}"))
    assert result.response_type == "refusal"
    assert result.answer == (
        "Please remove identity or account details from your question and ask it again. "
        "This assistant does not read PAN, Aadhaar, phone numbers, email addresses, or OTPs."
    )
    assert secret not in result.answer
    assert [item.url for item in result.citations] == list(EDUCATION_URLS)
