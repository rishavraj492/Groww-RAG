"""Run the submission question bank against the fixture API and print JSON."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "scheme_facts.json"
CHROMA = Path(__file__).resolve().parents[1] / "data" / "chroma"

QUESTIONS = [
    ("Q01", "What is the expense ratio of HDFC Mid Cap?", None),
    ("Q02", "What is the exit load of HDFC Mid Cap?", None),
    ("Q03", "What is the minimum SIP of HDFC Mid Cap?", None),
    ("Q04", "What is the riskometer of HDFC Mid Cap?", None),
    ("Q05", "What is the benchmark of HDFC Mid Cap?", None),
    ("Q06", "What is the expense ratio of HDFC Small Cap?", None),
    ("Q07", "What is the ELSS lock-in period?", None),
    ("Q08", "What is the ELSS lock-in of HDFC Large Cap?", None),
    ("Q09", "How do I download a capital gains statement?", None),
    ("Q10", "What is the expense ratio?", None),
    ("Q11", "and the exit load?", "hdfc-mid-cap"),
    ("Q12", "Should I invest in HDFC Mid Cap?", None),
    ("Q13", "Which of these is better?", None),
    ("Q14", "What are the returns of HDFC Mid Cap?", None),
    ("Q15", "My PAN is ABCDE1234F. What is the exit load of HDFC Mid Cap?", None),
    ("Q16", "What is the expense ratio of Axis Mid Cap?", None),
    ("Q17", "Is the expense ratio good?", None),
    ("Q18", "What is a riskometer?", None),
    ("Q19", "Mid cap and small cap expense ratio", None),
    ("Q20", "What is the NAV of HDFC Mid Cap?", None),
]


def main() -> None:
    client = TestClient(create_app(FIXTURE, chroma_path=CHROMA))
    rows = []
    with client:
        health = client.get("/api/health").json()
        for qid, question, prior in QUESTIONS:
            body: dict = {"question": question}
            if prior:
                body["priorSchemeId"] = prior
            response = client.post("/api/query", json=body)
            data = response.json()
            citations = data.get("citations") or []
            scheme = data.get("scheme")
            rows.append(
                {
                    "id": qid,
                    "question": question,
                    "prior": prior,
                    "status": response.status_code,
                    "responseType": data.get("responseType"),
                    "queryType": data.get("queryType"),
                    "answer": (data.get("answer") or "")[:280],
                    "scheme": scheme.get("id") if isinstance(scheme, dict) else scheme,
                    "citation": citations[0].get("url") if citations else None,
                }
            )
    print(json.dumps({"health": health, "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
