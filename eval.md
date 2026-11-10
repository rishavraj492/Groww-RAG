# Evaluation

Pass or fail each phase of the facts-only mutual fund FAQ assistant. The gates come from [implementation-plan.md](implementation-plan.md). The product rules come from [architecture.md](architecture.md) and [problemStatement.md](problemStatement.md). Corner inputs are listed in [edge-case.md](edge-case.md).

A phase passes only when every check in its gate is true. Later phases add behavior. They do not relax an earlier gate.

## How to score

Mark each check **pass** or **fail**. A phase gate is **pass** only when all of its checks pass. Record the command, the date, and a one-line result next to any failure.

| Result | Meaning |
| --- | --- |
| Pass | The check’s “Pass when” condition was observed |
| Fail | The condition was absent, or a “Must not” item happened |
| Deferred | The check belongs to a later phase. Do not fail the current phase for it |

Cases marked **gap** in `edge-case.md` are not phase gates. Note the behavior you observed. Fail the phase only when that behavior invents a number, gives advice, calls the model on a refusal, or cites a URL outside the corpus.

## Rules for every phase

- Default `pytest` does not fetch `groww.in`, `www.hdfcfund.com`, `www.sebi.gov.in`, `investor.sebi.gov.in`, or `www.amfiindia.com`.
- Default `pytest` does not call a live model and does not read `LLM_API_KEY`.
- `LLM_API_KEY` is never committed and never sent to the browser.
- The scheme set is the five HDFC ids in the architecture. None of them is an ELSS scheme.
- Labeled numbers come from `scheme_facts.json`. The model is not asked for those values.
- Advice and personal-data questions stop at the classifier.
- A user question does not fetch a page and does not add a URL.

Run the offline suite from `backend/`:

```text
pytest
```

Run the API from `backend/` and the web app from `frontend/` only when a check names them:

```text
uvicorn app.main:app
npm run dev
```

## Evidence to keep

| Phase | Keep |
| --- | --- |
| 0–6 | `pytest` exit code and the names of any failed tests |
| 1, 4, 6 | The fixture `scheme_facts.json` fields named in the gate. Do not commit live `scheme_facts.json`, `manifest.json`, `data/raw/`, or `data/chroma/` |
| 3, 5 | One sample JSON body for factual, refusal, and unavailable |
| 7 | Screenshot or notes for the disclaimer, a factual reply, a refusal, a clarification, and the follow-up after a refusal |
| Live | Capture date from health, citation URL opened, and whether the stated fact was on that page |

---

## Phase 0 — Scaffold

**Question.** Can a developer install dependencies, start the API, start the web app, and run an empty test suite?

**Setup.** Backend dependencies installed. Frontend dependencies installed. No facts file and no model key are required.

| ID | Check | Pass when |
| --- | --- | --- |
| E0-01 | `GET /api/health` | `uvicorn app.main:app` from `backend/` returns a successful health response. `factsLoaded` may be false. |
| E0-02 | Web placeholder | `npm run dev` in `frontend/` shows the project title. |
| E0-03 | Tests | `pytest` from `backend/` exits 0. |
| E0-04 | Config | `config.py` defines question cap `500`, passage cap `4`, holdings cap `10`, LLM timeout default `20`, facts path, Chroma path, and embedding model default `BAAI/bge-small-en-v1.5`. Education URLs are the AMFI investor page, the SEBI investor page, and `https://groww.in/learn/mutual-funds`. The retrieval score floor is a named constant. |
| E0-05 | Env template | `backend/.env.example` documents `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS`, `FACTS_PATH`, `CHROMA_PATH`, and `EMBEDDING_MODEL`. |
| E0-06 | Gitignore | `.env`, `__pycache__`, `node_modules`, `backend/data/raw/`, `backend/data/chroma/`, `backend/data/scheme_facts.json`, `backend/data/manifest.json`, and frontend build output are ignored. `sources.yaml` and `backend/data/fixtures/` are not ignored. |
| E0-07 | CORS | The API allows the Vite dev origin. |

**Must not.** A committed `.env`, a real API key in the repo, or a test that calls the network.

**Deferred.** Scheme data, classifier, `POST /api/query`, embeddings, and the chat transcript.

---

## Phase 1 — Corpus

**Question.** Are the five schemes data, and does a saved page become structured facts without the network?

**Setup.** Phase 0 gate passed. Fixture HTML and `sources.yaml` are present. Run ingest with `--source fixture` only.

| ID | Check | Pass when |
| --- | --- | --- |
| E1-01 | Registry | Exactly these ids and Groww URLs: `hdfc-mid-cap`, `hdfc-small-cap`, `hdfc-large-cap`, `hdfc-silver-etf-fof`, `hdfc-multi-cap`. |
| E1-02 | Catalog | Each of those entries has `document_type: scheme_page` and `authority: platform`. |
| E1-03 | Required URL removed | A test reads `sources.yaml` and fails. It does not fetch. |
| E1-04 | Allowlist | A catalog URL whose host is outside `groww.in`, `www.hdfcfund.com`, `www.sebi.gov.in`, `investor.sebi.gov.in`, and `www.amfiindia.com` is rejected. Ingest exits before any fetch when a required Groww URL is missing. |
| E1-05 | Fixture loader | The loader returns the mid-cap expense ratio from `backend/data/fixtures/scheme_facts.json`. |
| E1-06 | Missing fact | The small-cap fixture leaves one field null. |
| E1-07 | Fixture ingest | `python scripts/ingest.py --source fixture` writes facts and makes no network call. |
| E1-08 | Labeled AUM | The stored fund size is the labeled value. The conflicting figure in the About paragraph is not stored. |
| E1-09 | Returns table | The returns table creates no fact field. |
| E1-10 | Absent label | A label that is not on the page stays null. The silver ETF FoF exit load is not copied from an equity scheme. |
| E1-11 | Holdings | At most 10 holdings are stored. |
| E1-12 | Offline suite | Default `pytest` does not call `groww.in`. |

**Must not.** Reading AUM from the About paragraph, creating fields from the returns table, rank table, or calculator, or inventing a value for a missing label.

**Deferred.** Answer sentences, the query API, passage embeddings, and `--source live`.

**Edge cases to note, not gate.** I-05, I-12, I-19, I-24, I-29 in `edge-case.md`.

---

## Phase 2 — Fact answers

**Question.** Can labeled fields be answered from the fixture, and do advice and personal data receive the fixed refusals, with no vector store and no model key?

**Setup.** Phase 1 gate passed. Evaluate `classify.py`, `resolve.py`, and `answer.py` through tests. Retrieval and the LLM client do not exist yet.

| ID | Check | Pass when |
| --- | --- | --- |
| E2-01 | Personal data | A PAN-shaped token, a 12-digit Aadhaar-shaped number, an email, a 10-digit phone number, or “OTP” together with digits classifies as `pii`. The logged text does not contain the identifier. |
| E2-02 | Advice | “Should I invest”, “which is better”, “will this outperform”, and “how much tax will I pay” classify as `advisory`. “Is the expense ratio good?” is `advisory`. |
| E2-03 | Factual field | “What is the exit load of HDFC Small Cap?” classifies as `factual`. |
| E2-04 | First match | A question that contains both an identifier and an advice phrase is `pii`. |
| E2-05 | Aliases | Each alias maps to one scheme. “Cap fund” maps to none. More than two schemes is ambiguous. |
| E2-06 | Two schemes | “Mid cap and small cap expense ratio” resolves to those two schemes and `expense_ratio`. |
| E2-07 | Definition vs field | “What is a riskometer?” with no scheme resolves to a definition, not a field. |
| E2-08 | ELSS | “What is the ELSS lock-in?” with no scheme resolves to `elss_lock_in`. “ELSS lock-in of HDFC Large Cap” uses that scheme’s category and exit load and does not apply a three-year rule. |
| E2-09 | Statement | “How do I download a capital gains statement?” resolves to `statement_download` and no scheme. |
| E2-10 | Tax note | “What tax note does the mid-cap page state?” resolves to `tax_note`. |
| E2-11 | Prior scheme | `priorSchemeId` is used only when the question names no scheme. |
| E2-12 | Template | The mid-cap expense-ratio sentence matches the fixture number, ends with “Last updated from sources: {accessed_at}”, and cites the Groww mid-cap URL. |
| E2-13 | Null field | A null expense ratio returns unavailable. When the scheme is known, the citation is that scheme’s Groww URL. |
| E2-14 | Two-scheme copy | Two schemes produce two sentences and two citations. The text contains none of “better”, “recommend”, or “should”. |
| E2-15 | Official citation rule | When `authority` is `official`, the citation is the official URL. Otherwise it is the Groww URL. Phase 6 supplies the official fixture. The rule itself must already be in the template. |
| E2-16 | NAV | A NAV reply includes `nav_date` and `accessed_at`. |
| E2-17 | Holdings | A holdings reply returns at most 10 rows from the record. |
| E2-18 | Isolation | Personal-data and advice strings never call a retriever or a model client. Tests do not import those modules. |
| E2-19 | Offline | Tests pass with no network and no API key. |

**Must not.** A refusal that includes a scheme number, a template that ranks the two schemes, or an ELSS three-year lock-in applied to HDFC Large Cap.

**Deferred.** HTTP status codes, education-link JSON, passage retrieval, and model drafts. Definition, ELSS, and statement resolutions are identified here and answered in Phase 5.

---

## Phase 3 — Query API

**Question.** Can a client ask a labeled-fact question, an advice question, or a personal-data question and receive the architecture’s JSON?

**Setup.** Phase 2 gate passed. Facts load from `FACTS_PATH`, defaulting to the fixture. Prose topics stay unavailable until Phase 5.

| ID | Check | Pass when |
| --- | --- | --- |
| E3-01 | Empty question | `POST /api/query` with an empty question returns 422. |
| E3-02 | Length | A question of 500 characters is accepted. A question of 501 characters returns 422. |
| E3-03 | Unknown prior | An unknown `priorSchemeId` returns 422, including when the question text names a valid scheme. |
| E3-04 | Mid-cap exit load | HTTP 200, `responseType: factual`, `queryType: factual`. The number matches the fixture. The citation URL is the scheme page on that fact. |
| E3-05 | Advice | “Should I invest in HDFC Mid Cap?” returns 200, `responseType: refusal`, `queryType: advisory`, the advisory template, and the education-link citations. The answer has no scheme number. |
| E3-06 | Personal data | A question with an email or PAN returns 200, `queryType: pii`, and the personal-data template. The identifier is absent from the answer and from the info log. The facts file is not opened for this request. |
| E3-07 | Null field | HTTP 200, `responseType: unavailable`, with the scheme URL when the scheme is known, and no guessed number. |
| E3-08 | Clarification | “What is the expense ratio?” with no scheme and no usable prior returns 200, `responseType: unavailable`, `queryType: factual`, and all five scheme names. No expense ratio appears. |
| E3-09 | Follow-up | “and the exit load?” with `priorSchemeId` `hdfc-mid-cap` returns the mid-cap exit load. |
| E3-10 | Prior ignored | A question that names small cap, sent with prior mid cap, answers small cap. |
| E3-11 | Prose topics | Definition, ELSS, and statement-download resolutions return unavailable copy that says the assistant does not have that in the current sources. |
| E3-12 | Schemes list | `GET /api/schemes` returns id, name, and Groww URL for the five schemes. It does not return expense ratios or other values. |
| E3-13 | Startup | A missing facts file exits the process with a log line that names `scripts/ingest.py`. Health includes scheme count and the oldest `accessed_at`. |
| E3-14 | Logs | Logs include `queryType`, scheme id, and whether the reply was structured, refused, or unavailable. They omit `pii` question text and the API key. |
| E3-15 | Offline | Tests do not fetch Groww and do not read `LLM_API_KEY`. |

**Payload shape.** Compare factual, refusal, and unavailable bodies to section 9 of the architecture. Refusal citations use the configured education URLs with `accessedAt` and `asOf` null. Two-scheme answers set `scheme` to null and include one citation per scheme. Clarification sets `scheme` to null.

**Must not.** A 500 for a refusal, a scheme value inside an advice or personal-data answer, or a clarification that includes a captured number.

**Deferred.** Real passage answers, the LLM client, official-source replacement, and the browser client. The chat client does not send `priorSchemeId` until Phase 7. The API must already honor it.

---

## Phase 4 — Passage index

**Question.** Can definitions, the general ELSS lock-in rule, and statement-download steps be retrieved from a local index, while labeled numbers still come from facts?

**Setup.** Phase 3 gate passed. Tests use a fake embedder. Do not download `BAAI/bge-small-en-v1.5` in the default suite.

| ID | Check | Pass when |
| --- | --- | --- |
| E4-01 | Catalog pages | `sources.yaml` records an ELSS lock-in page, short definition pages for expense ratio, riskometer, and exit load, and a Groww help or learn page for capital-gains and account-statement downloads. `scheme_id` is empty. `topic` is `elss_lock_in`, `definition`, or `statement_download`. `authority` follows the host. |
| E4-02 | Chunks | Prose is split on headings into passages of about 500 tokens with a small overlap. |
| E4-03 | Metadata | Each passage has `source_url`, `title`, `authority`, `document_type`, `scheme_id`, `topic`, `accessed_at`, and `as_of`. General documents use an empty `scheme_id`. Metadata values are strings. |
| E4-04 | Exclusions | The Phase 1 returns table produces no passage. Rank tables, calculator output, the About paragraph, and holdings produce no passages. |
| E4-05 | Statement retrieval | A fixture help page about downloading a capital gains statement is retrieved for that question, with its URL and `accessed_at`. |
| E4-06 | Definition retrieval | The retriever returns the definition passage for a known definition question. |
| E4-07 | Score floor | The floor in `config.py` is set so that known definition passes and an unrelated question returns nothing. |
| E4-08 | Filters and order | A resolved scheme and topic filter the search. The top 4 are kept. Official passages are ordered before platform passages. A result below the floor does not call a model. |
| E4-09 | PDF | A PDF with no text layer is `failed` in the manifest. A text-layer PDF is extracted with `pypdf`. |
| E4-10 | Model pin | On startup the process refuses to serve when the manifest’s embedding model name differs from `EMBEDDING_MODEL`. |
| E4-11 | Query API unchanged | Definition, ELSS, and statement questions still receive the Phase 3 unavailable reply. |
| E4-12 | Fake embedder | Default tests do not download `BAAI/bge-small-en-v1.5`. |
| E4-13 | Facts still win | A labeled expense-ratio question still uses `scheme_facts.json`, not a chunk. |

**Must not.** Indexing the About paragraph or the returns table, querying vectors built by a different embedding model, or calling the LLM from this phase.

**Deferred.** Prose sentences shown to the user, and the live embedding download. A real index may be built outside the default test run.

---

## Phase 5 — Grounded generation

**Question.** Are prose questions answered in two to four sentences from the retrieved passages, and does a number or URL outside those passages become unavailable?

**Setup.** Phase 4 gate passed. Tests use a fake LLM client. Default `pytest` never contacts a live model host.

| ID | Check | Pass when |
| --- | --- | --- |
| E5-01 | Prompt | The system prompt requires: use only the supplied passages; set `grounded` false and leave `answer` empty when the fact is missing; add no number, date, or name from outside the passages; do not recommend a scheme or describe expected performance; cite only passage `source_url` values; respond with JSON only. |
| E5-02 | User message | The user message contains the question and each passage’s URL, capture date, authority, and text. A prose prompt contains only the retrieved passage text. |
| E5-03 | Client | The client calls `{LLM_BASE_URL}/chat/completions` with bearer auth, temperature `0`, a JSON response format, and `LLM_TIMEOUT_SECONDS`. It parses `choices[0].message.content`. |
| E5-04 | ELSS prose | “What is the ELSS lock-in period?” is answered from the indexed education passage. The citation is that passage’s URL. |
| E5-05 | Statement prose | “How do I download a capital gains statement?” is answered from the help passage. The scheme object is null. |
| E5-06 | Below the floor | Retrieval below the floor does not call the client and returns unavailable. |
| E5-07 | Field bypass | “What is the expense ratio of HDFC Mid Cap?” uses the fact template and does not call the fake client. |
| E5-08 | Refusal bypass | An advisory question and a `pii` question do not call the fake client. |
| E5-09 | Ungrounded | `grounded: false`, an empty answer, or unparseable JSON becomes HTTP 200 unavailable. |
| E5-10 | Bad citation | A citation URL that was not retrieved is dropped. Zero remaining URLs becomes unavailable. |
| E5-11 | Bad number | A percentage, rupee amount, or other number in the answer that is absent from the concatenated passage text becomes unavailable. |
| E5-12 | Primary citation | The primary citation is the first surviving official URL, otherwise the first surviving URL. `accessedAt` comes from that passage. |
| E5-13 | Provider failure | Timeout, HTTP error, invalid JSON, or a client exception returns HTTP 200 unavailable. The raw passage is not returned as the answer. |
| E5-14 | Length | The answer is length-capped before it reaches the client. |
| E5-15 | Logs | Model latency is logged when a model was called. The API key and the full prompt are absent at info level. |
| E5-16 | Offline | Default `pytest` never contacts a live model host. |

**Must not.** Falling back to the raw passage after a failed guard, putting a labeled expense ratio through the model, or returning a 500 for a provider failure.

**Deferred.** Replacing a matching Groww citation with an AMC, SEBI, or AMFI URL. That is Phase 6. The guard’s official-first order is already in E5-12.

---

## Phase 6 — Official sources

**Question.** When an AMC, SEBI, or AMFI page and a Groww page state the same fact, are the spoken value and the citation the official ones?

**Setup.** Phase 5 gate passed. Evaluate with fixtures. A live official fetch stays on `--source live` and is outside this gate.

| ID | Check | Pass when |
| --- | --- | --- |
| E6-01 | Catalog | `sources.yaml` includes official URLs for the five schemes’ factsheets or scheme information documents, and for the SEBI or AMFI pages that define expense ratio, riskometer, and ELSS lock-in. Hosts stay on the allowlist. |
| E6-02 | One hop | A SID link discovered on a scheme page is fetched in the same live run only when its host is allowlisted. The crawl stops after that hop. |
| E6-03 | Match | When the normalized official value and the Groww value match, the stored value and URL are the official ones, with `authority: official`. |
| E6-04 | Conflict | When they differ, the stored spoken value is the official one, `conflict: true` is set, and the Groww value is kept as `platform_value` on the manifest. The values are not averaged. |
| E6-05 | Matching fixture | The answer cites the official URL. |
| E6-06 | Conflicting fixture | The answer cites the official URL and speaks the official number. The Groww value is not the number in the sentence. |
| E6-07 | Retrieval order | Official passages still sort before platform passages. The guard’s primary citation follows that order. |
| E6-08 | Definition example | An example number on a definition page does not overwrite a scheme’s captured expense ratio. |
| E6-09 | Offline | These checks use fixtures. Default `pytest` does not perform a live official fetch. |

**Must not.** Averaging the two numbers, citing Groww when an official value was stored, or speaking `platform_value` in the answer.

**Deferred.** A chat control that explains the conflict. The sentence still uses the official value.

---

## Phase 7 — Chat and acceptance

**Question.** Can a person ask questions in the browser, follow up about the same scheme, and read the answer with a source link and a capture date?

Evaluate in two steps. The fixture step is the phase gate for the UI. The live step is the problem statement’s success criteria and runs once after ingest.

### Fixture UI

**Setup.** The UI points at the fixture API. No live model is required for labeled facts.

| ID | Check | Pass when |
| --- | --- | --- |
| E7-01 | Disclaimer | This sentence stays visible before and after a reply: the assistant shares public facts from HDFC scheme sources and does not give investment advice. |
| E7-02 | Capture line | Health’s oldest capture date is shown as “Sources last captured”. |
| E7-03 | Chips | Chips exist for the five schemes plus expense ratio, exit load, minimum SIP, and how to download a capital gains statement. A scheme chip fills a question that includes that scheme name. Chips do not answer locally. |
| E7-04 | Submit | The submit control disables while the request runs and enables when the response arrives. |
| E7-05 | Factual render | A mid-cap expense-ratio question renders the template sentence and a link to the Groww URL in the payload, plus authority and “Last updated from sources” from `accessedAt`. |
| E7-06 | Refusal render | “Which fund is better?” renders the refusal and the AMFI link and does not render an expense ratio. |
| E7-07 | Clarification render | A field question with no scheme and no prior lists all five names and no number. The client does not guess a scheme. |
| E7-08 | Follow-up | After a mid-cap factual reply, “and the exit load?” sends `priorSchemeId` `hdfc-mid-cap` and returns the mid-cap exit load. |
| E7-09 | Refusal clears prior | After a refusal, the next field question with no scheme asks for a scheme again. The client does not send `priorSchemeId`. |
| E7-10 | Unavailable prior | The client does not send `priorSchemeId` after an unavailable reply that has no scheme. |
| E7-11 | 422 | HTTP 422 shows the validation message and keeps the typed question. |
| E7-12 | Network error | A network failure shows a retry message and leaves the transcript in place. |
| E7-13 | Client boundary | The client does not call a model, rank schemes, compute returns, or send earlier answers as evidence. |
| E7-14 | Regression | `pytest` still passes on fixtures with no live fetch and no live model. |

**Must not.** The disclaimer disappearing after a reply, a chip that answers without `POST /api/query`, or a follow-up that still carries a scheme after a refusal.

### Live acceptance

**Setup.** Run `python scripts/ingest.py --source live`. Point `FACTS_PATH` and `CHROMA_PATH` at the generated files. Set `LLM_API_KEY`. Ask in the UI.

| ID | Check | Pass when |
| --- | --- | --- |
| E7-15 | Health | Health shows five schemes, a passage count, the embedding model name, and a capture date. |
| E7-16 | Required labels | Each scheme has non-null `expense_ratio`, `exit_load`, `minimum_sip`, `riskometer`, and `benchmark`, or an explicit null in the manifest for that label. |
| E7-17 | Named scheme | Expense ratio, exit load, minimum SIP, riskometer, and benchmark for one named scheme match the cited page. |
| E7-18 | ELSS | The general ELSS lock-in question is answered from the education passage. The lock-in question for HDFC Large Cap uses that scheme’s category and exit load and does not apply the three-year rule. |
| E7-19 | Statement | “How do I download a capital gains statement?” is answered from the help passage, with no scheme object. |
| E7-20 | Clarification chain | “What is the expense ratio?” with no scheme lists the five names. After a mid-cap answer, “and the exit load?” returns the mid-cap exit load. |
| E7-21 | Advice | “Should I invest in HDFC Mid Cap?” and “Which of these is better?” are refusals and contain no scheme number. |
| E7-22 | Outside corpus | A scheme or fact that is not in the corpus contains no invented number. |
| E7-23 | Open the citation | For each factual reply, the stated fact is on the cited page. When Phase 6 stored an official value, the citation is the official page. |
| E7-24 | Provider removed | With the key removed or `LLM_BASE_URL` pointed at a closed port, a labeled-fact question still answers and a prose question returns HTTP 200 unavailable. |

**Must not.** A live NAV recomputed at question time, a return or tax calculation, or an advice answer produced by the model.

This live pass is manual. It is not part of default `pytest`.

---

## Regression

Run the earlier gate again after each later phase. A new phase fails if it breaks an earlier check.

| After | Re-run |
| --- | --- |
| Phase 2 | Phase 1 fixture ingest and the no-network assertion |
| Phase 3 | Phase 2 classifier, resolver, and template checks through the HTTP API |
| Phase 4 | Phase 3 factual, refusal, clarification, and unavailable bodies. Prose routes still return the Phase 3 unavailable copy |
| Phase 5 | E3-04, E3-05, E3-08, and E5-07. Labeled facts still bypass the client |
| Phase 6 | E2-14 and E5-04. Official citation replaces Groww only for fields stored as official |
| Phase 7 | Default `pytest` (E7-14), then the fixture UI checks, then the live checklist |

## Problem-statement success criteria

Use the live acceptance step to judge the product, not a single phase in isolation.

| Criterion | Checks |
| --- | --- |
| Expense ratio, exit load, minimum SIP, riskometer, benchmark, ELSS lock-in, and statement download match the cited source | E7-17, E7-18, E7-19, E7-23 |
| Advice and “which is better” are refused | E7-06, E7-21 |
| Schemes or facts outside the corpus are not answered with invented numbers | E7-22 |
| A reader can open the citation and find the stated fact | E7-23 |
| The interface states that answers are public facts and not investment advice | E7-01 |
| Personal data is refused without a model call | E2-01, E3-06, E5-08 |

## Score sheet

Copy this table for a review. One row per phase.

| Phase | Gate | Date | pytest | Failures |
| --- | --- | --- | --- | --- |
| 0 Scaffold |  |  |  |  |
| 1 Corpus |  |  |  |  |
| 2 Fact answers |  |  |  |  |
| 3 Query API |  |  |  |  |
| 4 Passage index |  |  |  |  |
| 5 Grounded generation |  |  |  |  |
| 6 Official sources |  |  |  |  |
| 7 Chat, fixture UI |  |  |  |  |
| 7 Live acceptance |  |  | n/a |  |

The build is ready for the problem statement when Phases 0–6 and the Phase 7 fixture UI are pass, and every live check E7-15 through E7-24 is pass on the same corpus refresh.
