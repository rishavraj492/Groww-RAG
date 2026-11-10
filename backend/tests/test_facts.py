from pathlib import Path

from app.services.facts import get_scheme, load_facts

FIXTURE_FACTS = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "scheme_facts.json"


def test_loader_returns_mid_cap_expense_ratio():
    facts = load_facts(FIXTURE_FACTS)
    mid_cap = get_scheme(facts, "hdfc-mid-cap")
    assert mid_cap is not None
    assert mid_cap["expense_ratio"] == "0.74%"
    assert mid_cap["authority"] == "platform"
    assert mid_cap["source_url"] == "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"
    assert len(mid_cap["holdings"]) <= 10


def test_small_cap_fixture_leaves_expense_ratio_null():
    small_cap = get_scheme(load_facts(FIXTURE_FACTS), "hdfc-small-cap")
    assert small_cap is not None
    assert small_cap["expense_ratio"] is None
    assert small_cap["exit_load"]
    assert small_cap["authority"] == "platform"


def test_loader_returns_none_for_an_unknown_scheme():
    assert get_scheme(load_facts(FIXTURE_FACTS), "not-a-scheme") is None
