# Implementation Plan

Phase-by-phase build of the facts-only mutual fund FAQ assistant in [problemStatement.md](problemStatement.md), following [architecture.md](architecture.md).

Each phase leaves the repo runnable and tested. Later phases add behavior on top of earlier ones. The default test suite does not fetch Groww, the AMC, SEBI, or AMFI, and it does not call a live model.

## How the phases map to the product

| Phase | Problem-statement step | What exists when the phase ends |
| --- | --- | --- |
| 0. Scaffold | — | Backend and frontend projects, config, and a test runner |
| 1. Corpus | Corpus capture for the five schemes | Scheme registry, `sources.yaml`, fixture facts, and ingest into `scheme_facts.json` |
| 2. Fact answers | Factual answers for labeled fields; refusals | Classifier, resolver, and answer templates on the fixture |
| 3. Query API | Question handling for facts, advice, and personal data | `POST /api/query` for structured facts, refusals, clarification, and unavailable |
| 4. Passage index | Definitions, ELSS lock-in, statement downloads | Heading chunks, local index, retrieval above a score floor |
| 5. Grounded generation | Prose answers checked against passages | Model drafts, citation and number guard, unavailable on failure |
| 6. Official sources | Citation preference | AMC, SEBI, and AMFI pages cited ahead of Groww when both state the same fact |
| 7. Chat | Response display and success criteria | Disclaimer, transcript, follow-up scheme, source link, and a live acceptance pass |
| 8. Daily refresh | Corpus capture on a schedule | GitHub Action runs live ingest at 10:00 Asia/Kolkata and commits refreshed facts, passages, and Chroma |

Clarification and `priorSchemeId` are part of the query API in Phase 3. The chat client starts sending that id in Phase 7.

## Working agreements

- Python 3.11+, FastAPI, and Pydantic on the backend. React + Vite on the frontend.
- Prose generation uses Groq through its OpenAI-compatible chat API, called only from the backend (`services/llm_client.py` via `POST /api/query`). The browser never talks to Groq and never receives `LLM_API_KEY`. `LLM_BASE_URL` defaults to `https://api.groq.com/openai/v1` and `LLM_MODEL` defaults to `openai/gpt-oss-120b`. Embeddings stay on the local model. Groq is not used to classify questions or to fill labeled scheme numbers. A prose question reaches Groq only after ingest has written a non-empty Chroma index.
- The scheme set is the five HDFC Groww pages in the architecture. None of them is an ELSS scheme.
- Labeled numbers (expense ratio, exit load, minimums, NAV, fund size, riskometer, benchmark, category) are read from `scheme_facts.json`. The model is not asked for those values.
- A passage is one prose field, not a 500-token window. On the live Groww pages that field is the investment objective, the tax note, the stamp-duty line, or one current fund manager’s education and experience. Nothing in those fields is longer than about 60 tokens, so scheme pages are not merged and not overlapped. A split with a small overlap applies only when a passage exceeds 400 tokens. Return tables, rank tables, the calculator, holdings, peer funds, expense history, the fund-house blurb, and the category-info block are not indexed.
- Advice and personal-data questions stop at the classifier. They do not retrieve and they do not call the model.
- Secrets stay in environment variables. `LLM_API_KEY` is never committed or sent to the browser.
- Out of scope for every phase: other schemes, live NAV or return math, tax owed by a person, accounts, portfolios, an always-on in-process crawler, and using a model to classify advice. Daily refresh is Phase 8: the same `scripts/ingest.py --source live` path, triggered by GitHub Actions, not a long-running crawler inside the API.

```text
backend/
  app/
    main.py
    config.py
    api/health.py
    api/schemes.py
    api/query.py
    schemas/request.py
    schemas/response.py
    schemas/facts.py
    services/classify.py
    services/resolve.py
    services/facts.py
    services/retrieve.py
    services/answer.py
    services/prompt.py
    services/llm_client.py
    services/guard.py
    services/query_service.py
  scripts/ingest.py
  data/sources.yaml
  data/fixtures/
  tests/
frontend/
  src/App.tsx
  src/api.ts
  src/components/Disclaimer.tsx
  src/components/Composer.tsx
  src/components/Transcript.tsx
.github/
  workflows/daily-ingest.yml
```

Create files in the phase that first needs them. Empty modules are not required up front.

---

## Phase 0 — Scaffold

**Outcome.** A developer can install dependencies, start the API, start the web app, and run an empty test suite.

**Tasks**

1. Create the backend package layout that this phase needs: `main.py`, `config.py`, and `api/health.py`. Add `backend/requirements.txt` with FastAPI, Uvicorn, Pydantic, httpx, PyYAML, pytest, beautifulsoup4, pypdf, chromadb, and sentence-transformers.
2. Add `backend/app/config.py` with question length cap `500`, passage cap `4`, holdings cap `10`, LLM timeout default `20`, facts path, Chroma path, and embedding model default `BAAI/bge-small-en-v1.5`. Default `LLM_BASE_URL` to `https://api.groq.com/openai/v1` and `LLM_MODEL` to `openai/gpt-oss-120b`. Read overrides from the environment. Put the education URLs here: `https://www.amfiindia.com/investor`, `https://investor.sebi.gov.in/`, and `https://groww.in/learn/mutual-funds`. Leave the retrieval score floor as a named constant; Phase 4 sets its value.
3. Add `backend/app/main.py` with a FastAPI app, CORS for the Vite dev origin, and `GET /api/health`. Until Phase 3, `factsLoaded` may be `false`.
4. Add `backend/.env.example` documenting `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS`, `FACTS_PATH`, `CHROMA_PATH`, and `EMBEDDING_MODEL`. `LLM_API_KEY` is the Groq API key. Show the Groq defaults for `LLM_BASE_URL` and `LLM_MODEL`.
5. Scaffold the Vite React app in `frontend/` with a single page that renders the project title.
6. Add a root `.gitignore` for `.env`, `__pycache__`, `node_modules`, `backend/data/raw/`, `backend/data/chroma/`, `backend/data/scheme_facts.json`, `backend/data/manifest.json`, and frontend build output. Keep `backend/data/sources.yaml` and `backend/data/fixtures/` commit-able.

**Done when**

- `uvicorn app.main:app` from `backend/` serves `GET /api/health`.
- `npm run dev` in `frontend/` shows the placeholder page.
- `pytest` from `backend/` exits 0.

---

## Phase 1 — Corpus

**Outcome.** The five schemes and their Groww URLs are data. A saved scheme page becomes structured facts. Labeled fields win over the “About” paragraph. Return tables never become facts. Tests and the fixture ingest path do not use the network.

**Tasks**

1. Add `backend/data/sources.yaml` with the five required scheme pages:

   | `scheme_id` | URL |
   | --- | --- |
   | `hdfc-mid-cap` | `https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth` |
   | `hdfc-small-cap` | `https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth` |
   | `hdfc-large-cap` | `https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth` |
   | `hdfc-silver-etf-fof` | `https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth` |
   | `hdfc-multi-cap` | `https://groww.in/mutual-funds/hdfc-multi-cap-fund-direct-growth` |

   Each entry has `document_type: scheme_page` and `authority: platform`.

2. Add a scheme registry used by ingest and the resolver: id, display name, Groww URL, and aliases from the architecture (`mid cap`, `small cap`, `large cap`, `silver`, `multi cap`, and the longer forms).

3. Add `backend/data/fixtures/scheme_facts.json` for two schemes, `hdfc-mid-cap` and `hdfc-small-cap`. Include expense ratio, exit load, minimum SIP, minimum lump sum, riskometer, benchmark, category, NAV value and NAV date, fund size, fund manager, stamp duty, tax note, a holdings list of at most 10 rows, `source_url`, `authority: platform`, and `accessed_at`. Leave one field null on the small-cap record so later tests can prove a missing fact becomes unavailable.

4. Add a loader in `backend/app/services/facts.py` that reads a facts file and looks up a scheme by id.

5. Add `backend/data/fixtures/hdfc_mid_cap.html` trimmed from the public page shape: labeled expense ratio, exit load, minimum SIP, fund size, NAV with a date, risk label, benchmark, investment objective, fund manager, stamp duty, tax note, and a short holdings table. Include an “About” paragraph whose fund-size figure disagrees with the labeled fund size. Include a small returns table.

6. Implement `backend/scripts/ingest.py`:
   - Read `sources.yaml`. Reject a URL whose host is outside `groww.in`, `www.hdfcfund.com`, `www.sebi.gov.in`, `investor.sebi.gov.in`, and `www.amfiindia.com`. Exit before any fetch if one of the five Groww URLs is missing.
   - `--source fixture` reads the saved HTML and does not use the network. `--source live` fetches allowlisted URLs at most once per second, with a 20-second timeout and a descriptive user agent. Store raw bodies under `data/raw/` by URL hash.
   - Set `accessed_at` to the UTC date of the run. A failed live fetch marks that URL `failed` in the manifest and keeps the previous good record.
   - Extract labeled facts from embedded page data when present, otherwise from label-value text. Map the labels listed in the architecture’s scheme fact record. The labeled fund size is the stored AUM. Do not read AUM from the “About” paragraph.
   - Store at most 10 holdings. Do not create fact fields from the returns table, rank table, or calculator.
   - Leave a label null when it is absent. Do not assume the silver ETF FoF uses the same exit-load sentence as the equity funds.
   - Write `scheme_facts.json` and `manifest.json`.

7. Add tests for the registry, the fixture loader, and the fixture ingest path. A test fails if a required Groww URL is removed from `sources.yaml`. That check is a YAML read and does not fetch. Ingest tests assert the labeled AUM is stored, the conflicting About figure is not, the returns table creates no field, and a missing label stays null.

**Done when**

- The registry lists exactly those five ids and URLs.
- The fixture loader returns the mid-cap expense ratio from the file.
- `python scripts/ingest.py --source fixture` writes facts for the fixture page with no network, and the stored fund size is the labeled value.
- Default `pytest` does not call `groww.in`.

---

## Phase 2 — Fact answers

**Outcome.** Expense ratio, exit load, minimum SIP, riskometer, and benchmark can be answered from the fixture. Advice and personal data receive the fixed refusals. No vector store and no model key are required.

**Tasks**

1. Implement `backend/app/services/classify.py`. First match wins.
   - `pii`: PAN-shaped token, 12-digit Aadhaar-shaped number, email, 10-digit phone number, or “OTP” together with digits. The classifier result must not need the raw identifier to be logged.
   - `advisory`: “should I”, “which is better”, “which fund”, “best fund”, “recommend”, “outperform”, “CAGR”, “returns”, “how much will I”, “how much should I invest”, “portfolio”, “good time”, “worth buying”, and “for my risk”. “Is the expense ratio good?” is advisory. “What is the exit load of HDFC Small Cap” is factual.
   - `factual`: every other question.
2. Implement `backend/app/services/resolve.py`.
   - Map aliases to one scheme. “Cap fund” alone matches none. More than two schemes is ambiguous.
   - Map field questions to `expense_ratio`, `exit_load`, `minimum_sip`, `minimum_lumpsum`, `riskometer`, `benchmark`, `category`, `nav`, `aum`, or fund-manager name.
   - “Mid cap and small cap expense ratio” resolves to two schemes and `expense_ratio`.
   - “What is a riskometer?” with no scheme resolves to a definition, not a field.
   - “What is the ELSS lock-in?” with no scheme resolves to topic `elss_lock_in`.
   - “ELSS lock-in of HDFC Large Cap” uses that scheme’s category and exit load. It does not apply a three-year rule.
   - “How do I download a capital gains statement?” resolves to topic `statement_download` and no scheme.
   - “How much tax will I pay?” is left to the classifier as advisory. “What tax note does the mid-cap page state?” resolves to `tax_note`.
   - Use `priorSchemeId` only when the question names no scheme.
3. Implement `backend/app/services/answer.py` templates. A field reply is one sentence plus “Last updated from sources: {accessed_at}”. NAV replies include the NAV date. Two schemes produce two sentences and two citations. The template does not contain “better”, “recommend”, or “should”. Citation is the official URL when `authority` is `official`, otherwise the Groww URL. A null field returns unavailable and, when the scheme is known, that scheme’s Groww URL. Holdings return at most `10` rows from the record.
4. Add `backend/tests/test_classify.py`, `test_resolve.py`, and `test_answer.py` for the cases in the architecture’s testing section.

**Done when**

- Personal-data and advice strings never call a retriever or a model client. Those modules do not exist yet, and the tests do not import them.
- The mid-cap expense-ratio fixture produces a sentence whose number matches the fixture and whose citation is the Groww mid-cap URL.
- A null expense ratio returns unavailable.
- Two schemes produce two sentences and no “better”.
- Tests pass offline.

---

## Phase 3 — Query API

**Outcome.** A client can ask a labeled-fact question, an advice question, or a personal-data question and receive the architecture’s JSON. A field question that names no scheme asks which of the five. Prose topics stay unavailable until Phase 5.

**Tasks**

1. Add Pydantic models in `schemas/request.py`, `schemas/response.py`, and `schemas/facts.py` matching the architecture: `question`, optional `priorSchemeId`, `responseType`, `queryType`, `answer`, `scheme`, and `citations` with `url`, `title`, `authority`, `accessedAt`, and `asOf`.
2. Implement `services/query_service.py` for this phase:
   - Classify first. `pii` and `advisory` return `responseType: refusal`, the templates from the architecture, and the education-link citations. Do not open the facts file for those questions.
   - Field questions call the Phase 2 templates.
   - A field question with no scheme and no usable `priorSchemeId` returns `responseType: unavailable` and lists the five scheme names.
   - `priorSchemeId` applies only when the new question names no scheme.
   - Definition, ELSS, and statement-download resolutions return unavailable with copy that says the assistant does not have that in the current sources. Phase 5 replaces this for passages that exist.
   - Unknown `priorSchemeId`, an empty question, or a question longer than 500 characters is HTTP 422.
3. Add `POST /api/query` and `GET /api/schemes`. Schemes returns id, name, and Groww URL only. It does not return expense ratios or other values.
4. Load facts at startup from `FACTS_PATH`, defaulting to the fixture in development. If the file is missing, exit with a log line that names `scripts/ingest.py`. Extend health with scheme count and the oldest `accessed_at`.
5. Log `queryType`, scheme id, and whether the reply was structured, refused, or unavailable. Do not log a `pii` question or the API key.
6. Add an API test on the fixture: 422 for an empty question, 422 for an unknown `priorSchemeId`, 200 factual for the mid-cap exit load, 200 refusal for “Should I invest in HDFC Mid Cap?”, 200 unavailable for a null field, 200 clarification for “What is the expense ratio?” with no scheme, and 200 for “and the exit load?” when `priorSchemeId` is `hdfc-mid-cap`.

**Done when**

- The factual payload’s number matches the fixture, and the citation URL is the scheme page recorded on that fact.
- Advice and personal-data requests do not read a scheme value into the answer.
- A question with no scheme lists the five names and includes no expense ratio.
- Tests do not fetch Groww and do not read `LLM_API_KEY`.

---

## Phase 4 — Passage index

**Outcome.** Prose from the five Groww scheme pages can be retrieved from a local index. Labeled scheme numbers still come from facts, not from chunks. Ingest in this phase reads only those five links. It does not add education, help, or regulatory URLs, and it does not ingest a PDF factsheet or scheme information document.

**What the saved pages imply.** Measured from `backend/data/raw/` on 2026-10-31. Four live bodies are on disk (small cap, large cap, silver ETF FoF, multi cap). The mid-cap raw body is missing, and the mid-cap record in `scheme_facts.json` matches the fixture page rather than the live shape of the other four, even though the manifest marks it `ok`. Re-fetch that URL before building a live index for it.

Each saved page is a Next.js document. The prose is in `props.pageProps.mfServerSideData`, not in long HTML sections. The longest single string worth considering is 44 estimated tokens, and every string that should be indexed is under 80 once a manager’s education and experience are joined. The sections that do run past 500 tokens are the holdings table (49 to 123 rows; silver has 3) and the fund-management block that lists other schemes. `historic_fund_expense` is 1,288 to 1,565 rows and must not become passages. Three equity pages share the same tax sentence, and all four share the same stamp-duty line and the same fund-house blurb dated 30 Sep 2017 (`₹2,70,046 Cr`). `category_info` on the three equity pages describes a contra fund, which these schemes are not. The silver exit load is `1%` within 15 days; the equity pages say within 1 year.

**Tasks**

1. Chunk and embed only the five scheme pages already listed in `sources.yaml`. Do not add any other URL. Do not fetch or parse a PDF factsheet or SID, and do not call `pypdf` for this phase. A live run that lacks the mid-cap raw body does not invent mid-cap passages from the fixture.
2. Write one passage per field. Do not pack fields up to 500 tokens, and do not overlap scheme-page passages. Prefix the heading onto short fields so the embedded text is searchable. Attach `source_url`, `title`, `authority`, `document_type`, `scheme_id`, `topic`, `accessed_at`, and `as_of`. Every passage uses one of the five scheme ids.
   - Live page, from `mfServerSideData`: `description` as `objective`; `category_info.tax_impact` as `tax_note`; `stamp_duty` as `stamp_duty`; each current manager’s `person_name`, `education`, and `experience` as its own `fund_manager` passage. Copy the source wording, including the silver objective’s grammar.
   - Fixture HTML, which has no embedded JSON: one passage per heading section, with the same metadata and the same exclusions. The mid-cap fixture objective is one sentence, the same shape as the live objectives.
   - If a passage ever exceeds 400 tokens, split it with a small overlap so it stays under the 512-token limit of `BAAI/bge-small-en-v1.5`. The scheme pages measured here do not hit that guard.
3. Do not write passages for return tables, rank tables, calculator output, the “About” paragraph, holdings, peer comparison, `analysis`, `meta_desc`, `historic_fund_expense`, `historic_exit_loads`, `funds_managed`, `amc_info.description`, or `category_info` description / helper / definition. The “Understand terms” block defines annualised and absolute returns; those questions are refused as advice before retrieval, so it is not indexed. Holdings stay on the fact record only. Exit load stays a structured fact and is not also a passage.
4. Keep the local embedding model `BAAI/bge-small-en-v1.5` (384 dimensions, 512-token context). Passages are short English. A larger model does not fix a wrong field in the passage. When embedding a question, prepend `Represent this sentence for searching relevant passages: `. Do not prepend that instruction to passages. Store the collection with cosine distance (`hnsw:space` cosine) so the score floor is a cosine distance. Replace that URL’s rows in the `chromadb` collection `scheme_passages`. Write the model name and passage count into the manifest. Provide a fake embedder in tests so `pytest` does not download the model.
5. Store embeddings with persistent `chromadb` on disk. The four saved pages yield about 20 passages (objective, tax note, stamp duty, and two manager bios each), and five schemes stay around 30. Metadata filters on `scheme_id` and `topic` do the retrieval; the equity tax sentences are identical, so an unfiltered search cannot tell those schemes apart. Do not add a hosted vector database. HNSW is already what local Chroma uses and is exact enough at this size.
6. Implement `services/retrieve.py`: embed the question with the query instruction, filter by `scheme_id` and `topic` when the resolver set them, take the top 4, drop the set when the best cosine distance is worse than the floor, and order `official` before `platform`.
7. Set the score floor in `config.py` from a few fixture passages so a known scheme-page passage passes and an unrelated question fails. Calibrate it on the one-sentence objective, not on a 500-token chunk.
8. On startup, refuse to serve if the manifest’s embedding model name differs from `EMBEDDING_MODEL`.
9. Keep the query API on the Phase 3 unavailable reply for prose until Phase 5. Add unit tests that the retriever returns the scheme-page passage and returns nothing below the floor. Assert the returns table, the About paragraph, and a contra-fund category description produce no passage.

**Done when**

- A fixture passage from the mid-cap scheme page, such as the investment objective, is retrieved for that question, with that page’s Groww URL and `accessed_at`.
- The returns table in the Phase 1 HTML fixture produces no passage.
- No passage comes from a PDF factsheet, a SID, or any URL other than the five Groww scheme links.
- Chunk metadata includes scheme, topic, authority, and capture date.
- A scheme page produces one passage per field above, and no passage longer than the 400-token split guard. The mid-cap fixture objective is retrieved as its own passage.
- Default tests use the fake embedder and do not download `BAAI/bge-small-en-v1.5`.

---

## Phase 5 — Grounded generation

**Outcome.** Prose questions are answered in two to four sentences from the retrieved passages. A number or a URL that is not in those passages becomes unavailable.

**Tasks**

1. Implement `services/prompt.py`. The system prompt requires: use only the supplied passages; set `grounded` false and leave `answer` empty when the fact is missing; add no number, date, or name from outside the passages; do not recommend a scheme or describe expected performance; cite only passage `source_url` values; respond with JSON only. The user message contains the question and each passage’s URL, capture date, authority, and text.
2. Add the generation schema: `grounded`, `answer`, and `citation_urls`.
3. Implement `services/llm_client.py` with `httpx` against `{LLM_BASE_URL}/chat/completions`. This is the only Groq call site. Default the base URL to Groq at `https://api.groq.com/openai/v1` and the model to `openai/gpt-oss-120b`. Send `Authorization: Bearer <LLM_API_KEY>`, temperature `0`, a JSON response format, and `LLM_TIMEOUT_SECONDS`. Cap completion tokens and set low reasoning effort so one reply fits the model’s minute budget. Groq stores a temperature of `0` as a tiny positive value; still send `0`. Parse `choices[0].message.content`.
4. Implement `services/guard.py`. `grounded: false`, an empty answer, or unparseable JSON becomes unavailable. Drop citation URLs that were not retrieved. Zero remaining URLs becomes unavailable. Every number, percentage, and rupee amount in the answer must appear in the concatenated passage text. Cap the answer length. The primary citation is the first surviving official URL, otherwise the first surviving URL, and `accessedAt` comes from that passage.
5. Wire `query_service.py`. Retrieval below the floor does not call the client. A field question does not call the client. An advisory or `pii` question does not call the client. On timeout, HTTP error, invalid JSON, or a failed guard, return HTTP 200 unavailable. Do not fall back to the raw passage after this phase.
6. Log model latency when a model was called. Do not log the API key or the full prompt at info level.
7. Add `test_guard.py` and `test_query_service.py` with a fake client. Assert a prose prompt contains only the retrieved passage text, a stray percentage becomes unavailable, an unknown citation is dropped, and a client exception becomes unavailable.

**Done when**

- “What is the ELSS lock-in period?” can be answered from the indexed education passage, and the reply’s citation is that passage’s URL.
- “How do I download a capital gains statement?” is answered from the help passage, with no scheme object.
- “What is the expense ratio of HDFC Mid Cap?” still uses the fact template and does not call the fake client.
- Default `pytest` never contacts a live model host.

---

## Phase 6 — Official sources

**Outcome.** When an AMC, SEBI, or AMFI page and a Groww page state the same fact, the spoken value and the citation are the official ones.

**Tasks**

1. Add official URLs to `sources.yaml` for the five schemes’ factsheets or scheme information documents, and for the SEBI or AMFI pages that define expense ratio, riskometer, and ELSS lock-in. Keep hosts on the allowlist. A SID link discovered on a scheme page may be fetched in the same live run only when its host is allowlisted. Stop after that one hop.
2. When ingest extracts the same field from an official document and from Groww, compare the normalized values. If they match, store the official value and URL with `authority: official`. If they differ, store the official value, set `conflict: true`, and keep the Groww value as `platform_value` on the manifest. Do not average them.
3. Confirm the Phase 2 citation rule now selects the official URL for that field. Retrieval already sorts official passages first. The guard’s primary citation must follow that order.
4. Add a fixture with the same expense ratio on a platform record and an official record, and a second fixture where the two values differ. Test that the answer cites the official URL in both cases and that the conflicting Groww value is not the spoken number.

**Done when**

- A matching official fact replaces the Groww citation.
- A conflicting official fact is the number in the sentence, and the manifest shows `conflict: true` plus `platform_value`.
- Tests use fixtures. A live official fetch stays on `--source live`.

---

## Phase 7 — Chat and acceptance

**Outcome.** A person can ask questions in the browser, follow up about the same scheme, and read the answer with a source link and capture date. The problem statement’s success criteria then pass once on the live corpus.

**Tasks**

1. Add `frontend/src/api.ts` for `GET /api/health`, `GET /api/schemes`, and `POST /api/query`. Point the base URL at the FastAPI dev server.
2. Build `Disclaimer`. Keep this sentence visible: the assistant shares public facts from HDFC scheme sources and does not give investment advice. Show the oldest capture date from health as “Sources last captured”.
3. Build `Composer`: one text field, a submit control that disables while the request runs, and suggestion chips for the five schemes plus expense ratio, exit load, minimum SIP, and how to download a capital gains statement. A chip that names a scheme fills a question that includes that scheme name. Chips do not answer locally.
4. Build `Transcript`:
   - Factual: answer, scheme name when present, one link per citation, authority, and “Last updated from sources” from `accessedAt`.
   - Refusal: the template and the education links, with no scheme facts beside them.
   - Unavailable: the template and the scheme link when the payload includes one. A clarification lists the five scheme names from the answer text and does not guess a scheme.
5. Compose these in `App.tsx`. The client renders the payload from `POST /api/query`. It does not call Groq or any other model, rank schemes, or compute returns. HTTP 422 shows the validation message and keeps the typed question. A network failure shows a retry message and leaves the transcript in place.
6. When the latest factual reply has a scheme id, send it as `priorSchemeId` on the next question. Do not send it after a refusal, or after an unavailable reply that has no scheme. Do not send earlier answers back as evidence.
7. Acceptance, after the UI works against the fixture API. Run `python scripts/ingest.py --source live` (or `--source fixture` for the saved mid-cap page) so `scheme_facts.json`, `passages.json`, and `data/chroma/` exist with a non-zero `passage_count` in the manifest. Point `FACTS_PATH` and `CHROMA_PATH` at those files in `backend/.env`, then restart the API. Confirm health shows five schemes (or the fixture set), `passageCount` greater than zero, the embedding model name, and a capture date. Each scheme has non-null `expense_ratio`, `exit_load`, `minimum_sip`, `riskometer`, and `benchmark`, or an explicit null in the manifest for that label. Set `LLM_API_KEY` on the backend only. Prose questions in the UI go to FastAPI, which calls Groq; ask:
   - Expense ratio, exit load, minimum SIP, riskometer, and benchmark for one named scheme.
   - The general ELSS lock-in question, and the lock-in question for HDFC Large Cap.
   - How to download a capital gains statement.
   - “What is the expense ratio?” with no scheme, then “and the exit load?” after a mid-cap answer.
   - “Should I invest in HDFC Mid Cap?” and “Which of these is better?”
   - A scheme or fact that is not in the corpus.
8. For each factual reply, open the citation and find the stated fact on that page. Official pages should be the citation when Phase 6 stored an official value. Then remove the key or point `LLM_BASE_URL` at a closed port. A labeled-fact question still answers. A prose question returns unavailable with HTTP 200.

**Done when**

- Against the fixture API, a mid-cap expense-ratio question renders the template sentence and a link to the Groww URL in the payload.
- “Which fund is better?” renders the refusal and the AMFI link, and does not render an expense ratio.
- A field question with no scheme and no prior id lists all five names and no number. After a mid-cap factual reply, “and the exit load?” returns the mid-cap exit load. After a refusal, the next field question with no scheme asks for a scheme again.
- The disclaimer remains on screen after a reply, and submit stays disabled until the response arrives.
- The live checklist passes in the browser. Advice replies contain no scheme number. An out-of-corpus question contains no invented number.
- `pytest` still passes on fixtures with no live fetch and no live model.

---

## Phase 8 — Daily corpus refresh

**Outcome.** Every day at 10:00 Asia/Kolkata, GitHub Actions runs the existing live ingest so scraping, normalization, cleaning, chunking, embedding, and Chroma writes happen against the current allowlisted pages. The API keeps loading facts and the index from disk; it still does not fetch sources on a user question.

**Tasks**

1. Add `.github/workflows/daily-ingest.yml` with:
   - `schedule` cron `30 4 * * *` (10:00 Asia/Kolkata / IST).
   - `workflow_dispatch` so a refresh can be run by hand.
   - A single job on `ubuntu-latest` that checks out the repo, sets up Python 3.11, installs `backend/requirements.txt`, and runs `python scripts/ingest.py --source live` from `backend/`.
2. Keep the job on the Phase 1–6 ingest path only. It must fetch allowlisted URLs, write raw bodies under `data/raw/`, extract and normalize labeled facts, merge official sources when present, chunk passages, embed with `BAAI/bge-small-en-v1.5`, and replace rows in the persistent Chroma collection under `data/chroma/`. It must not call Groq, classify questions, or start the API.
3. After a successful ingest, commit and push the refreshed generated corpus on the default branch: `backend/data/scheme_facts.json`, `backend/data/passages.json`, `backend/data/manifest.json`, `backend/data/raw/`, and `backend/data/chroma/`. Use a bot-style commit message that names the UTC `accessed_at` date. Skip the commit step when `git status` is clean. Do not commit `.env`, secrets, or `__pycache__`.
4. Fail the workflow when ingest exits non-zero, when any of the five required Groww scheme pages is `failed` in the manifest, when `passage_count` is 0, or when the manifest `embedding_model` is not `BAAI/bge-small-en-v1.5`. A single non-required official or regulatory URL may stay `failed` if the previous good record for that URL is kept, matching the existing ingest rules.
5. Give the workflow `contents: write` so it can push. Document in the workflow comments that the Action needs permission to push to the default branch and that no `LLM_API_KEY` is required for this job. Cache the Hugging Face / sentence-transformers model directory when practical so the daily embed step is not a cold download every run.
6. Confirm default `pytest` is unchanged: it still uses fixtures and a fake embedder, and it still does not fetch Groww or open a live model host. Manual verification is a `workflow_dispatch` run plus a local API restart pointed at the refreshed `FACTS_PATH` and `CHROMA_PATH`, then a health check that shows a new `oldestAccessedAt` or an updated `passageCount`.

**Done when**

- The workflow file exists and is scheduled for 10:00 Asia/Kolkata, with a manual dispatch option.
- A successful run updates facts, passages, the manifest, raw captures, and Chroma from live allowlisted pages without calling Groq.
- A failed required Groww fetch fails the job; the previous good corpus remains in git until a successful run commits a replacement.
- Pulling the updated branch and starting the API serves the new capture date without any change to `POST /api/query`.
- Default `pytest` still passes offline.

## Suggested sequence

Finish Phases 0–3 before downloading the embedding model or requesting a Groq API key. Phase 3 already demonstrates refusals, labeled facts, and clarification. Phase 4 needs the local embedding model only for a real index; its tests use a fake embedder. Phase 5 is the first phase that needs `LLM_API_KEY` on the backend, and its tests use a fake client so they do not contact Groq. Until ingest has populated Chroma, prose answers stay unavailable and the backend does not call Groq. The chat in Phase 7 talks only to FastAPI; after Phases 5 and 6 and a loaded index, prose questions trigger the backend Groq client before the live acceptance pass. Phase 8 comes after that acceptance pass: schedule the same live ingest in GitHub Actions so the corpus refreshes daily without changing the query path.
