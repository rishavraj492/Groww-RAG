"""Rule classifier. The first match wins: personal data, then advice, then factual."""

import logging
import re

logger = logging.getLogger(__name__)

PII = "pii"
ADVISORY = "advisory"
FACTUAL = "factual"

_PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE)
_AADHAAR = re.compile(r"(?<!\d)(?:\d{12}|\d{4}[\s-]\d{4}[\s-]\d{4})(?!\d)")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+91[\s-]?)?(?:\d{10}|\d{5}[\s-]\d{5})(?!\d)")
_OTP = re.compile(r"\botp\b", re.IGNORECASE)
_DIGIT = re.compile(r"\d")

# "good" covers "Is the expense ratio good?". "better" covers "which is better"
# and "Which of these is better?".
_ADVISORY = re.compile(
    "|".join(
        (
            r"\bshould i\b",
            r"\bwhich is better\b",
            r"\bwhich funds?\b",
            r"\bbest funds?\b",
            r"\brecommend",
            r"\boutperform",
            r"\bcagr\b",
            r"\breturns\b",
            r"\bhow much will i\b",
            r"\bhow much should i invest\b",
            r"\bhow much tax will i\b",
            r"\bportfolio\b",
            r"\bgood time\b",
            r"\bworth buying\b",
            r"\bfor my risk\b",
            r"\bbetter\b",
            r"\bgood\b",
        )
    ),
    re.IGNORECASE,
)


def classify(question: str) -> str:
    """Label a question as pii, advisory, or factual.

    The return value and the log line are only that label. The question text
    is not logged, so a personal-data identifier never has to be written down.
    """
    query_type = _query_type(question or "")
    logger.info("queryType=%s", query_type)
    return query_type


def _query_type(question: str) -> str:
    if (
        _PAN.search(question)
        or _AADHAAR.search(question)
        or _EMAIL.search(question)
        or _PHONE.search(question)
    ):
        return PII
    if _OTP.search(question) and _DIGIT.search(question):
        return PII
    if _ADVISORY.search(question):
        return ADVISORY
    return FACTUAL
