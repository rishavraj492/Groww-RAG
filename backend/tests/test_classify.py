import logging

import pytest

from app.services.classify import classify


@pytest.mark.parametrize(
    ("question", "secret"),
    [
        ("My PAN is ABCDE1234F", "ABCDE1234F"),
        ("pan abcde1234f is mine", "abcde1234f"),
        ("email me at investor@example.com", "investor@example.com"),
        ("call 9876543210", "9876543210"),
        ("call +91 9876543210", "9876543210"),
        ("aadhaar 1234 5678 9012", "1234 5678 9012"),
        ("id 123456789012", "123456789012"),
        ("the OTP is 459120", "459120"),
    ],
)
def test_personal_data_is_pii_and_the_log_omits_the_identifier(question, secret, caplog):
    with caplog.at_level(logging.INFO):
        assert classify(question) == "pii"
    assert caplog.records[0].getMessage() == "queryType=pii"
    assert secret not in caplog.text
    assert question not in caplog.text


def test_personal_data_wins_over_advice(caplog):
    question = "Should I invest? My PAN is ABCDE1234F"
    with caplog.at_level(logging.INFO):
        assert classify(question) == "pii"
    assert "ABCDE1234F" not in caplog.text
    assert question not in caplog.text


def test_otp_without_digits_is_not_personal_data():
    assert classify("What is an OTP?") == "factual"


@pytest.mark.parametrize(
    "question",
    [
        "Should I invest in HDFC Mid Cap?",
        "which is better",
        "Which of these is better?",
        "will this outperform",
        "how much tax will I pay",
        "Is the expense ratio good?",
        "which fund should I pick",
        "what is the best fund",
        "please recommend a scheme",
        "what is the CAGR",
        "what are the returns of mid cap",
        "how much will I earn",
        "how much should I invest",
        "build my portfolio",
        "is this a good time to buy",
        "is it worth buying",
        "a fund for my risk",
    ],
)
def test_advice_phrases_are_advisory(question):
    assert classify(question) == "advisory"


@pytest.mark.parametrize(
    "question",
    [
        "What is the exit load of HDFC Small Cap",
        "What is the expense ratio of HDFC Mid Cap?",
        "What is the expense ratio of HDFC Mid Cap Fund Direct Growth?",
        "What is the minimum SIP of HDFC Large Cap?",
        "What is a riskometer?",
        "What is the ELSS lock-in?",
        "How do I download a capital gains statement?",
    ],
)
def test_fact_questions_stay_factual(question):
    assert classify(question) == "factual"


def test_phase2_modules_do_not_import_a_retriever_or_model_client():
    import importlib
    import sys

    import app.services.answer as answer
    import app.services.classify as classify
    import app.services.resolve as resolve

    sys.modules.pop("app.services.retrieve", None)
    sys.modules.pop("app.services.llm_client", None)
    importlib.reload(answer)
    importlib.reload(classify)
    importlib.reload(resolve)
    assert "app.services.retrieve" not in sys.modules
    assert "app.services.llm_client" not in sys.modules
