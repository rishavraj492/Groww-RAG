import json
import math
import sys
from pathlib import Path

from app.config import PASSAGE_CAP, RETRIEVAL_SCORE_FLOOR
from app.services.embeddings import EMBEDDING_DIMENSIONS, QUERY_PREFIX
from app.services.index import COLLECTION_NAME, index_passages, open_collection
from app.services.passages import TOKEN_SPLIT_AT, chunk_scheme_html, estimate_tokens
from app.services.registry import REQUIRED_GROWW_URLS, SCHEME_BY_ID
from app.services.retrieve import retrieve
from scripts.ingest import run_ingest
from tests.fake_embedder import MATCH_DISTANCE, MISS_DISTANCE, FakeEmbedder

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SOURCES = DATA_DIR / "sources.yaml"
FIXTURES = DATA_DIR / "fixtures"
MID_CAP = SCHEME_BY_ID["hdfc-mid-cap"]
OBJECTIVE = (
    "Investment objective: To generate long-term capital appreciation from a portfolio "
    "invested predominantly in equity and equity related securities of mid-cap companies."
)
OBJECTIVE_QUESTION = "What is the investment objective of HDFC Mid Cap?"
UNRELATED_QUESTION = "How do I bake sourdough bread at home?"


def test_score_floor_keeps_the_short_objective_and_drops_an_unrelated_question():
    assert MATCH_DISTANCE < RETRIEVAL_SCORE_FLOOR < MISS_DISTANCE
    embedder = FakeEmbedder()
    embedder.embed([OBJECTIVE])
    matched = embedder.embed([QUERY_PREFIX + OBJECTIVE_QUESTION])[0]
    missed = embedder.embed([QUERY_PREFIX + UNRELATED_QUESTION])[0]
    passage = embedder.embed([OBJECTIVE])[0]
    assert _cosine_distance(matched, passage) <= RETRIEVAL_SCORE_FLOOR
    assert _cosine_distance(missed, passage) > RETRIEVAL_SCORE_FLOOR
    assert estimate_tokens(OBJECTIVE) <= TOKEN_SPLIT_AT


def test_fixture_objective_is_retrieved_with_its_source_and_exclusions_are_absent(tmp_path):
    embedder = FakeEmbedder()
    chroma_path = tmp_path / "chroma"
    result = run_ingest(
        "fixture",
        sources_path=SOURCES,
        facts_path=tmp_path / "scheme_facts.json",
        manifest_path=tmp_path / "manifest.json",
        fixtures_dir=FIXTURES,
        accessed_at="2026-10-31",
        chroma_path=chroma_path,
        embedder=embedder,
        client_factory=_reject_network,
    )
    assert result["manifest"]["passage_count"] == len(result["passages"]) == 4
    assert result["manifest"]["embedding_model"] == embedder.model_name
    assert {row["source_url"] for row in result["passages"]} == {MID_CAP.url}

    collection = open_collection(chroma_path)
    assert collection.name == COLLECTION_NAME
    assert collection.metadata["hnsw:space"] == "cosine"
    stored = collection.get(include=["documents", "metadatas"])
    blob = json.dumps(stored["documents"])
    assert "₹12,000" not in blob
    assert "18.41%" not in blob
    assert "22.17%" not in blob
    assert "₹9,87,654" not in blob
    assert "Persistent Systems" not in blob
    assert "Contra funds" not in blob

    hits = retrieve(
        OBJECTIVE_QUESTION,
        embedder=embedder,
        collection=collection,
        scheme_id="hdfc-mid-cap",
        topic="objective",
    )
    assert len(hits) == 1
    hit = hits[0]
    assert hit.text == OBJECTIVE
    assert hit.source_url == MID_CAP.url
    assert hit.title == MID_CAP.name
    assert hit.authority == "platform"
    assert hit.document_type == "scheme_page"
    assert hit.scheme_id == "hdfc-mid-cap"
    assert hit.topic == "objective"
    assert hit.accessed_at == "2026-10-31"
    assert hit.as_of == "2026-10-30"
    assert hit.distance <= RETRIEVAL_SCORE_FLOOR
    assert hit.distance < 0.15
    assert estimate_tokens(hit.text) <= TOKEN_SPLIT_AT
    assert {item.source_url for item in hits} <= set(REQUIRED_GROWW_URLS)

    assert (
        retrieve(
            UNRELATED_QUESTION,
            embedder=embedder,
            collection=collection,
            scheme_id="hdfc-mid-cap",
            topic="objective",
        )
        == []
    )
    questions = [text for text in embedder.seen if text.startswith(QUERY_PREFIX)]
    passages = [text for text in embedder.seen if not text.startswith(QUERY_PREFIX)]
    assert questions
    assert passages
    assert all(not text.startswith(QUERY_PREFIX) for text in passages)
    assert "sentence_transformers" not in sys.modules


def test_contra_category_description_is_not_a_passage():
    html = """
    <script id="__NEXT_DATA__" type="application/json">
    {"props": {"pageProps": {"mfServerSideData": {
      "description": "The scheme is seek to capital appreciation by investing in units of HDFC Silver ETF.",
      "category_info": {
        "description": "Contra funds follow Contrarian strategy which means investing in stocks in contrast to the prevailing sentiment.",
        "tax_impact": "If you redeem within two years, returns are taxed as per your Income Tax slab."
      },
      "stamp_duty": "0.005% (from July 1st, 2020)"
    }}}}
    </script>
    <h2>About</h2>
    <p>The fund size of this scheme is ₹12,000 Cr according to this overview.</p>
    <h2>Returns</h2>
    <p>1Y annualised returns 18.41%</p>
    """
    passages = chunk_scheme_html(
        html,
        scheme_id="hdfc-silver-etf-fof",
        source_url=SCHEME_BY_ID["hdfc-silver-etf-fof"].url,
        title=SCHEME_BY_ID["hdfc-silver-etf-fof"].name,
        authority="platform",
        document_type="scheme_page",
        accessed_at="2026-10-31",
        as_of=None,
    )
    blob = json.dumps(passages)
    assert "Contra funds" not in blob
    assert "₹12,000" not in blob
    assert "18.41%" not in blob
    assert {row["source_url"] for row in passages} <= set(REQUIRED_GROWW_URLS)
    assert chunk_scheme_html("%PDF-1.7", document_type="scheme_page", **_mid_cap_kwargs()) == []


def test_scheme_filter_separates_identical_text(tmp_path):
    text = "Tax implication: Equity funds follow the page tax implication rules for investors."
    small = SCHEME_BY_ID["hdfc-small-cap"]
    passages = [
        _row(text, MID_CAP, topic="tax_note"),
        _row(text, small, topic="tax_note"),
    ]
    embedder = FakeEmbedder()
    collection = index_passages(tmp_path / "chroma", passages, embedder)
    hits = retrieve(
        "What tax implication does the page state?",
        embedder=embedder,
        collection=collection,
        scheme_id="hdfc-mid-cap",
        topic="tax_note",
    )
    assert [hit.source_url for hit in hits] == [MID_CAP.url]
    assert hits[0].scheme_id == "hdfc-mid-cap"


def test_official_passages_sort_ahead_of_closer_platform_passages(tmp_path):
    platform = _row("Platform objective sentence for ordering.", MID_CAP, topic="objective")
    official = _row(
        "Official objective sentence for ordering.",
        MID_CAP,
        topic="objective",
        authority="official",
        source_url="https://www.hdfcfund.com/mid-cap-objective",
    )
    query = _basis(0)
    embedder = _ScriptedEmbedder(
        query,
        {
            platform["text"]: _at(0.05, 1),
            official["text"]: _at(0.30, 2),
        },
    )
    collection = index_passages(tmp_path / "chroma", [platform, official], embedder)
    hits = retrieve(
        OBJECTIVE_QUESTION,
        embedder=embedder,
        collection=collection,
        scheme_id="hdfc-mid-cap",
        topic="objective",
    )
    assert [hit.authority for hit in hits] == ["official", "platform"]
    assert hits[0].distance > hits[1].distance
    assert hits[0].source_url == "https://www.hdfcfund.com/mid-cap-objective"
    assert any(text.startswith(QUERY_PREFIX) for text in embedder.seen)


def test_empty_scheme_filter_keeps_only_general_passages(tmp_path):
    general = _row(
        "A riskometer is the scheme risk label printed on the page.",
        MID_CAP,
        topic="definition",
        source_url="https://www.amfiindia.com/investor",
    )
    general["scheme_id"] = ""
    scheme = _row(OBJECTIVE, MID_CAP, topic="objective")
    embedder = _ScriptedEmbedder(
        _basis(0),
        {general["text"]: _at(0.05, 1), scheme["text"]: _at(0.05, 2)},
    )
    collection = index_passages(tmp_path / "chroma", [general, scheme], embedder)
    hits = retrieve(
        "What is a riskometer?",
        embedder=embedder,
        collection=collection,
        scheme_id="",
        topic="definition",
    )
    assert [hit.source_url for hit in hits] == ["https://www.amfiindia.com/investor"]
    assert hits[0].scheme_id == ""


def test_retrieval_returns_at_most_four_passages(tmp_path):
    passages = [
        _row(f"Investment objective number {index} for the mid cap page.", MID_CAP, topic="objective")
        for index in range(6)
    ]
    close = _at(0.05, 1)
    embedder = _ScriptedEmbedder(_basis(0), {passage["text"]: close for passage in passages})
    collection = index_passages(tmp_path / "chroma", passages, embedder)
    hits = retrieve(
        OBJECTIVE_QUESTION,
        embedder=embedder,
        collection=collection,
        scheme_id="hdfc-mid-cap",
        topic="objective",
    )
    assert len(hits) == PASSAGE_CAP == 4


def test_reindex_replaces_rows_for_that_url(tmp_path):
    path = tmp_path / "chroma"
    first = _row("Investment objective: alpha version of the mid cap objective.", MID_CAP, topic="objective")
    second = _row("Investment objective: beta version of the mid cap objective.", MID_CAP, topic="objective")
    embedder = FakeEmbedder()
    index_passages(path, [first], embedder)
    index_passages(path, [second], embedder)
    stored = open_collection(path).get(include=["documents"])
    assert stored["documents"] == [second["text"]]


def test_retriever_tests_do_not_load_the_local_embedding_model():
    assert "sentence_transformers" not in sys.modules


class _ScriptedEmbedder:
    def __init__(self, query_vector: list[float], passage_vectors: dict[str, list[float]]) -> None:
        self.query_vector = query_vector
        self.passage_vectors = passage_vectors
        self.seen: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            self.seen.append(text)
            if text.startswith(QUERY_PREFIX):
                vectors.append(self.query_vector)
            else:
                vectors.append(self.passage_vectors[text])
        return vectors


def _row(text: str, scheme, *, topic: str, authority: str = "platform", source_url: str | None = None) -> dict:
    return {
        "text": text,
        "source_url": source_url or scheme.url,
        "title": scheme.name,
        "authority": authority,
        "document_type": "scheme_page",
        "scheme_id": scheme.scheme_id,
        "topic": topic,
        "accessed_at": "2026-10-31",
        "as_of": "2026-10-30",
    }


def _mid_cap_kwargs() -> dict:
    return {
        "scheme_id": "hdfc-mid-cap",
        "source_url": MID_CAP.url,
        "title": MID_CAP.name,
        "authority": "platform",
        "accessed_at": "2026-10-31",
        "as_of": None,
    }


def _basis(slot: int) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[slot] = 1.0
    return vector


def _at(distance: float, slot: int) -> list[float]:
    similarity = 1.0 - distance
    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[0] = similarity
    vector[slot] = math.sqrt(max(0.0, 1.0 - similarity * similarity))
    return vector


def _cosine_distance(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    return 1.0 - dot


def _reject_network():
    raise AssertionError("fixture ingest must not open an HTTP client")
