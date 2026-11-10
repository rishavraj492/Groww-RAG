import pytest

from app.services.resolve import resolve


@pytest.mark.parametrize(
    ("question", "scheme_id"),
    [
        ("hdfc mid cap", "hdfc-mid-cap"),
        ("mid cap", "hdfc-mid-cap"),
        ("midcap", "hdfc-mid-cap"),
        ("HDFC Mid Cap Fund Direct Growth", "hdfc-mid-cap"),
        ("hdfc small cap", "hdfc-small-cap"),
        ("small cap", "hdfc-small-cap"),
        ("smallcap", "hdfc-small-cap"),
        ("hdfc large cap", "hdfc-large-cap"),
        ("large cap", "hdfc-large-cap"),
        ("largecap", "hdfc-large-cap"),
        ("silver etf", "hdfc-silver-etf-fof"),
        ("silver fof", "hdfc-silver-etf-fof"),
        ("silver", "hdfc-silver-etf-fof"),
        ("HDFC Silver ETF FoF Direct Growth", "hdfc-silver-etf-fof"),
        ("hdfc multi cap", "hdfc-multi-cap"),
        ("multi cap", "hdfc-multi-cap"),
        ("multicap", "hdfc-multi-cap"),
    ],
)
def test_each_alias_maps_to_one_scheme(question, scheme_id):
    result = resolve(question)
    assert result.scheme_ids == (scheme_id,)


@pytest.mark.parametrize(
    "question",
    [
        "Cap fund",
        "the cap fund",
        "What is the expense ratio of cap fund?",
    ],
)
def test_cap_fund_matches_no_scheme(question):
    assert resolve(question).scheme_ids == ()


def test_two_schemes_and_expense_ratio():
    result = resolve("Mid cap and small cap expense ratio")
    assert result.kind == "field"
    assert result.field == "expense_ratio"
    assert result.scheme_ids == ("hdfc-mid-cap", "hdfc-small-cap")
    assert result.ambiguous is False


def test_scheme_order_follows_the_question():
    result = resolve("small cap and mid cap expense ratio")
    assert result.scheme_ids == ("hdfc-small-cap", "hdfc-mid-cap")


def test_more_than_two_schemes_is_ambiguous():
    result = resolve("expense ratio of mid cap, small cap, and large cap")
    assert result.ambiguous is True
    assert result.kind == "ambiguous"
    assert result.scheme_ids == ()


def test_riskometer_without_a_scheme_is_a_definition():
    result = resolve("What is a riskometer?")
    assert result.kind == "definition"
    assert result.topic == "definition"
    assert result.field is None
    assert result.scheme_ids == ()


@pytest.mark.parametrize(
    "question",
    [
        "What is an expense ratio?",
        "What is an exit load?",
        "what does a riskometer mean",
    ],
)
def test_term_questions_without_a_scheme_are_definitions(question):
    result = resolve(question)
    assert result.kind == "definition"
    assert result.scheme_ids == ()


def test_definition_ignores_prior_scheme():
    result = resolve("What is a riskometer?", prior_scheme_id="hdfc-mid-cap")
    assert result.kind == "definition"
    assert result.scheme_ids == ()


def test_scheme_riskometer_is_a_field():
    result = resolve("What is the riskometer of HDFC Mid Cap?")
    assert result.kind == "field"
    assert result.field == "riskometer"
    assert result.scheme_ids == ("hdfc-mid-cap",)


def test_general_elss_lock_in_has_no_scheme():
    result = resolve("What is the ELSS lock-in?")
    assert result.kind == "elss_lock_in"
    assert result.topic == "elss_lock_in"
    assert result.scheme_ids == ()


def test_general_elss_ignores_prior_scheme():
    result = resolve("What is the ELSS lock-in?", prior_scheme_id="hdfc-large-cap")
    assert result.kind == "elss_lock_in"
    assert result.scheme_ids == ()


def test_elss_lock_in_of_a_scheme_uses_category_and_exit_load():
    result = resolve("ELSS lock-in of HDFC Large Cap")
    assert result.kind == "scheme_lock_in"
    assert result.scheme_ids == ("hdfc-large-cap",)
    assert result.fields == ("category", "exit_load")
    assert result.topic is None
    assert result.field is None


def test_statement_download_has_no_scheme():
    result = resolve("How do I download a capital gains statement?")
    assert result.kind == "statement_download"
    assert result.topic == "statement_download"
    assert result.scheme_ids == ()


def test_statement_download_ignores_a_named_scheme_and_prior_scheme():
    result = resolve(
        "How do I download a capital gains statement for HDFC Mid Cap?",
        prior_scheme_id="hdfc-small-cap",
    )
    assert result.kind == "statement_download"
    assert result.scheme_ids == ()


def test_tax_note_question_resolves_to_the_field():
    result = resolve("What tax note does the mid-cap page state?")
    assert result.kind == "field"
    assert result.field == "tax_note"
    assert result.scheme_ids == ("hdfc-mid-cap",)


def test_personal_tax_question_is_not_the_page_tax_note():
    result = resolve("How much tax will I pay?")
    assert result.field != "tax_note"


def test_prior_scheme_is_used_when_the_question_names_none():
    result = resolve("and the exit load?", prior_scheme_id="hdfc-mid-cap")
    assert result.kind == "field"
    assert result.field == "exit_load"
    assert result.scheme_ids == ("hdfc-mid-cap",)


def test_prior_scheme_is_ignored_when_the_question_names_one():
    result = resolve("What is the exit load of small cap?", prior_scheme_id="hdfc-mid-cap")
    assert result.scheme_ids == ("hdfc-small-cap",)
    assert result.field == "exit_load"


def test_prior_scheme_is_ignored_for_a_question_with_no_field():
    result = resolve("hello", prior_scheme_id="hdfc-mid-cap")
    assert result.kind == "unknown"
    assert result.scheme_ids == ()


@pytest.mark.parametrize(
    ("question", "field", "scheme_id"),
    [
        ("What is the expense ratio of HDFC Mid Cap?", "expense_ratio", "hdfc-mid-cap"),
        ("What is the exit load of HDFC Small Cap", "exit_load", "hdfc-small-cap"),
        ("minimum SIP for large cap", "minimum_sip", "hdfc-large-cap"),
        ("minimum lump sum for multi cap", "minimum_lumpsum", "hdfc-multi-cap"),
        ("riskometer of silver", "riskometer", "hdfc-silver-etf-fof"),
        ("benchmark of hdfc large cap", "benchmark", "hdfc-large-cap"),
        ("category of midcap", "category", "hdfc-mid-cap"),
        ("NAV of smallcap", "nav", "hdfc-small-cap"),
        ("fund size of the mid cap fund", "aum", "hdfc-mid-cap"),
        ("Who is the fund manager of HDFC Multi Cap?", "fund_manager", "hdfc-multi-cap"),
    ],
)
def test_field_questions_map_to_one_scheme_and_field(question, field, scheme_id):
    result = resolve(question)
    assert result.kind == "field"
    assert result.field == field
    assert result.scheme_ids == (scheme_id,)


def test_holdings_and_objective():
    holdings = resolve("What are the holdings of HDFC Small Cap?")
    assert holdings.kind == "holdings"
    assert holdings.scheme_ids == ("hdfc-small-cap",)

    objective = resolve("What is the investment objective of HDFC Mid Cap?")
    assert objective.kind == "prose"
    assert objective.topic == "objective"
    assert objective.scheme_ids == ("hdfc-mid-cap",)

    detail = resolve("Who is the fund manager of mid cap in more detail?")
    assert detail.kind == "prose"
    assert detail.topic == "fund_manager"
    assert detail.scheme_ids == ("hdfc-mid-cap",)
