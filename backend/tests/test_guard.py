"""Citation and number checks for a prose draft. No model and no network."""

import json

from app.config import ANSWER_MAX_CHARS, ANSWER_MAX_SENTENCES
from app.services.guard import guard
from app.services.retrieve import Passage

ELSS_URL = "https://www.amfiindia.com/investor"
HELP_URL = "https://groww.in/help/elss"
ELSS_TEXT = "ELSS schemes have a lock-in period of 3 years."


def test_grounded_false_empty_answer_and_bad_json_are_unavailable():
    passages = [_passage()]
    assert guard(_draft(ELSS_TEXT, [ELSS_URL], grounded=False), passages) is None
    assert guard(_draft("   ", [ELSS_URL]), passages) is None
    assert guard("the lock-in is 3 years", passages) is None
    assert guard(_draft(ELSS_TEXT, []), passages) is None


def test_unknown_citation_is_dropped_and_a_missing_url_is_unavailable():
    passages = [_passage()]
    kept = guard(_draft(ELSS_TEXT, ["https://evil.example/nope", ELSS_URL]), passages)
    assert kept is not None
    assert kept.answer == ELSS_TEXT
    assert [item.url for item in kept.citations] == [ELSS_URL]

    assert guard(_draft(ELSS_TEXT, ["https://evil.example/nope"]), passages) is None


def test_stray_percentage_or_rupee_amount_is_unavailable():
    passages = [_passage(text="The stamp duty line says ₹100 and the lock-in is 3 years.")]
    assert guard(_draft("The lock-in is 3 years and the fee is 12%.", [ELSS_URL]), passages) is None
    assert guard(_draft("The stamp duty is ₹200.", [ELSS_URL]), passages) is None
    kept = guard(_draft("The stamp duty is ₹100.", [ELSS_URL]), passages)
    assert kept is not None
    assert kept.answer == "The stamp duty is ₹100."


def test_a_shorter_number_does_not_match_inside_a_longer_one():
    passages = [_passage(text="The period is 30 years.")]
    assert guard(_draft("The period is 3 years.", [ELSS_URL]), passages) is None


def test_primary_citation_is_the_official_url_and_uses_its_capture_date():
    official = _passage(accessed_at="2026-10-31", authority="official", source_url=ELSS_URL, title="AMFI")
    platform = _passage(
        text="Groww also says the lock-in period is 3 years.",
        source_url=HELP_URL,
        title="Groww help",
        authority="platform",
        accessed_at="2026-10-01",
        document_type="help",
        topic="elss_lock_in",
    )
    result = guard(
        _draft("The lock-in period is 3 years.", [HELP_URL, ELSS_URL]),
        [platform, official],
    )
    assert result is not None
    assert [item.url for item in result.citations] == [ELSS_URL, HELP_URL]
    assert result.citations[0].authority == "official"
    assert result.citations[0].accessed_at == "2026-10-31"
    assert result.citations[0].title == "AMFI"


def test_answer_is_capped_at_four_sentences_and_the_character_limit():
    sentences = "Alpha stays. Beta stays. Gamma stays. Delta stays. Zebra goes."
    capped = guard(_draft(sentences, [ELSS_URL]), [_passage(text=sentences)])
    assert capped is not None
    assert capped.answer.count(".") == ANSWER_MAX_SENTENCES
    assert "Zebra" not in capped.answer
    assert "Delta stays." in capped.answer

    long_answer = " ".join(["token"] * 300)
    shortened = guard(_draft(long_answer, [ELSS_URL]), [_passage(text="token")])
    assert shortened is not None
    assert len(shortened.answer) <= ANSWER_MAX_CHARS
    assert shortened.answer.startswith("token")


def _passage(**overrides) -> Passage:
    values = {
        "text": ELSS_TEXT,
        "source_url": ELSS_URL,
        "title": "AMFI investor education",
        "authority": "official",
        "document_type": "regulatory",
        "scheme_id": "",
        "topic": "elss_lock_in",
        "accessed_at": "2026-10-31",
        "as_of": None,
        "distance": 0.05,
    }
    values.update(overrides)
    return Passage(**values)


def _draft(answer: str, urls: list[str], *, grounded: bool = True) -> str:
    return json.dumps({"grounded": grounded, "answer": answer, "citation_urls": urls})
