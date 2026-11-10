# Deployment Plan — Railway

Deploy the facts-only mutual fund FAQ assistant ([problemStatement.md](problemStatement.md), [implementation-plan.md](implementation-plan.md)) on [Railway](https://railway.com).

The app is a monorepo: FastAPI in `backend/`, React + Vite in `frontend/`. Production uses **two Railway services** from the same repo. The API loads facts and Chroma from disk at startup and calls Groq only for prose answers. The browser never receives `LLM_API_KEY`.

```text
GitHub repo
  ├── backend/   → Railway service "api"     (Python / Uvicorn)
  └── frontend/  → Railway service "web"     (static Vite build)

Browser ──HTTPS──▶ web (Railway domain)
                      │
                      └── VITE_API_BASE_URL ──HTTPS──▶ api (Railway domain)
                                                         ├── scheme_facts.json + chroma/ (in image)
                                                         └── Groq (LLM_API_KEY, prose only)
```

Daily corpus refresh stays on GitHub Actions (Phase 8). A successful ingest commit triggers a Railway redeploy so the API picks up new facts and passages without scraping on user questions.

---

## Goals

- Public HTTPS URLs for the chat UI and the query API
- Secrets only in Railway variables (never in the frontend build beyond the public API base URL)
- API starts only when facts and a non-empty Chroma index are present
- CORS limited to the Railway frontend origin
- Redeploy automatically on push to the default branch

Out of scope for this plan: a custom domain (optional later), a hosted vector DB, an in-process crawler, and running live ingest inside the Railway container on every boot.

---

## Prerequisites

1. Railway account and a GitHub (or other git) remote for this repo.
2. Groq API key for prose answers (`LLM_API_KEY`).
3. A committed corpus the API can load:
   - `backend/data/scheme_facts.json`
   - `backend/data/manifest.json` (with `passage_count` > 0 and `embedding_model: BAAI/bge-small-en-v1.5`)
   - `backend/data/chroma/` (persistent Chroma files)
   - Prefer a successful `python scripts/ingest.py --source live` (or fixture) committed via Phase 8 before the first deploy.
4. Python 3.11+ and Node 20+ locally only if you verify builds before pushing.

---

## Recommended topology

| Railway service | Root directory | Role |
| --- | --- | --- |
| `api` | `backend` | FastAPI: `/api/health`, `/api/schemes`, `/api/query` |
| `web` | `frontend` | Vite production build served on `$PORT` |

Use **public domains** on both services so the browser can call the API. Private Railway networking is unnecessary for this SPA → API pattern.

Do **not** put both processes in one service unless you later bake the SPA into FastAPI. Two services keep root directories, build caches, and restarts separate.

---

## Code changes required before deploy

These are not optional for a working Railway URL. Implement them in the repo, then deploy.

### 1. CORS from the environment

`backend/app/config.py` currently hardcodes localhost only:

```python
CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)
```

Change to read a comma-separated `CORS_ORIGINS` env var and keep the localhost defaults for local Vite. On Railway set:

```text
CORS_ORIGINS=https://<web-public-domain>
```

Use the exact frontend origin (scheme + host, no trailing slash). After the web domain is generated, set this on `api` and redeploy `api`.

### 2. Frontend production start script

`frontend/package.json` has `dev`, `build`, and `preview`, but no production start. Add:

```json
"start": "vite preview --host 0.0.0.0 --port $PORT"
```

On Windows locally `$PORT` is not required; Railway injects `PORT`. If the shell form is awkward on Windows, prefer a tiny `serve` dependency or a `Caddyfile` / Nixpacks static config later. For Railway Linux, `vite preview --host 0.0.0.0 --port $PORT` is enough.

### 3. Bake `VITE_API_BASE_URL` at build time

`frontend/src/api.ts` already reads `import.meta.env.VITE_API_BASE_URL`. Vite inlines that value during `npm run build`. Set it as a Railway variable on `web` **before** the build runs:

```text
VITE_API_BASE_URL=https://<api-public-domain>
```

No trailing slash. After the API domain changes, redeploy `web` so the new URL is baked in.

### 4. Optional but useful: health check path

Expose `GET /api/health` as the Railway healthcheck path on `api` so a failed facts/index load does not receive traffic.

### 5. Optional: pin a Procfile / `railway.toml`

Not required if service settings set build and start commands. If you prefer config-as-code:

- `backend/railway.toml` — start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- `frontend/railway.toml` — build `npm ci && npm run build`, start `npm run start`

Root directory still must be set in the Railway dashboard (or CLI) to `/backend` and `/frontend`.

---

## Environment variables

### Service `api` (root: `backend`)

| Variable | Required | Value |
| --- | --- | --- |
| `LLM_API_KEY` | Yes (for prose) | Groq key. Labeled-fact answers work without it; prose returns unavailable. |
| `LLM_BASE_URL` | No | Default `https://api.groq.com/openai/v1` |
| `LLM_MODEL` | No | Default `openai/gpt-oss-120b` |
| `LLM_TIMEOUT_SECONDS` | No | Default `20` |
| `FACTS_PATH` | Yes for live corpus | `data/scheme_facts.json` |
| `CHROMA_PATH` | Yes for live corpus | `data/chroma` |
| `EMBEDDING_MODEL` | No | Must match manifest: `BAAI/bge-small-en-v1.5` |
| `CORS_ORIGINS` | Yes in prod | Frontend public origin, e.g. `https://web-production-xxxx.up.railway.app` |
| `PORT` | Injected | Do not set manually; Uvicorn binds `$PORT` |

Never set `LLM_API_KEY` on the frontend service.

### Service `web` (root: `frontend`)

| Variable | Required | Value |
| --- | --- | --- |
| `VITE_API_BASE_URL` | Yes | API public origin, e.g. `https://api-production-xxxx.up.railway.app` |
| `PORT` | Injected | Used by `vite preview` |

Reference sibling services when possible, e.g. `VITE_API_BASE_URL=https://${{api.RAILWAY_PUBLIC_DOMAIN}}` and `CORS_ORIGINS=https://${{web.RAILWAY_PUBLIC_DOMAIN}}`, then redeploy both after domains exist.

---

## Create the Railway project

1. Create a new Railway project and connect the GitHub repository.
2. Add service **api** from the same repo.
   - Settings → Root Directory: `backend`
   - Build: Nixpacks / default Python detection, or `pip install -r requirements.txt`
   - Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Healthcheck path: `/api/health`
   - Watch paths (optional): `backend/**`
3. Add service **web** from the same repo.
   - Settings → Root Directory: `frontend`
   - Build: `npm ci && npm run build`
   - Start: `npm run start` (after adding the script above)
   - Watch paths (optional): `frontend/**`
4. Generate a public domain on **api**, then on **web**.
5. Set variables on both services (table above). Redeploy so CORS and the baked Vite URL take effect.
6. Confirm deploy logs: `api` must not exit with “Passage index … is empty” or a missing facts path.

---

## Build and runtime notes

### Python / embeddings

`chromadb` and `sentence-transformers` pull heavy wheels. Prefer a Railway plan with enough RAM for the first prose query (model load of `BAAI/bge-small-en-v1.5`). Labeled-fact questions do not load the embedder; prose questions call `build_embedder` lazily on first use.

Cold start tips:

- Cache Hugging Face downloads in the image only if you add a Dockerfile that pre-downloads the model. Nixpacks alone downloads on first embed unless the layer is warmed.
- Keep `EMBEDDING_MODEL` identical to the manifest or startup exits.
- Do not run `scripts/ingest.py --source live` as the Railway start command. Ingest belongs in GitHub Actions; the container only serves.

### Corpus on disk

Startup calls `require_facts` and `require_loaded_index`. If `scheme_facts.json` is missing, or the manifest claims passages but Chroma is empty, the process exits. Ship the generated corpus in git (Phase 8) or copy it into the image at build time. Ephemeral Railway disks alone are not enough: a redeploy loses uncommitted Chroma.

### CORS and browsers

Browser calls go from the `web` origin to the `api` origin. Without the frontend origin in `CORS_ORIGINS`, the chat UI shows a network failure even when `/api/health` works in curl.

### Groq limits

Defaults match Groq base limits for `openai/gpt-oss-120b` (see `backend/app/config.py`). Production traffic shares that budget. Timeouts and guard failures remain HTTP 200 unavailable, not 500.

---

## Deploy order (first time)

1. Merge CORS + frontend `start` script changes.
2. Ensure live (or fixture) corpus files are on the default branch.
3. Deploy **api** first; open `https://<api>/api/health` and confirm `factsLoaded`, `schemeCount`, `passageCount`, and `embeddingModel`.
4. Deploy **web** with `VITE_API_BASE_URL` pointing at that API domain.
5. Set `CORS_ORIGINS` on **api** to the web domain; redeploy **api**.
6. Open the web URL; ask a labeled-fact question and an advice question; confirm citation links and the disclaimer.

---

## Daily refresh → Railway

Phase 8 already schedules live ingest at 10:00 Asia/Kolkata and pushes updated `scheme_facts.json`, `passages.json`, `manifest.json`, `raw/`, and `chroma/`.

On Railway:

1. Keep **api** set to redeploy on the default branch.
2. After a successful Action push, Railway rebuilds **api** with the new corpus.
3. **web** does not need a redeploy for corpus-only commits (use watch paths so only `backend/**` triggers `api`).
4. No `LLM_API_KEY` is required in GitHub Actions for ingest.

If the Action fails, the previous corpus remains in git and the last good Railway deploy keeps serving.

---

## Verification checklist

After deploy:

- [ ] `GET https://<api>/api/health` → `factsLoaded: true`, `passageCount` > 0, expected embedding model
- [ ] `GET https://<api>/api/schemes` → five scheme ids (or the fixture set)
- [ ] From the web UI: expense ratio / exit load for a named scheme → factual answer + citation
- [ ] “Should I invest in HDFC Mid Cap?” → refusal + education links, no scheme number
- [ ] “What is the expense ratio?” with no scheme → clarification listing schemes
- [ ] Follow-up “and the exit load?” after a mid-cap answer uses `priorSchemeId`
- [ ] Prose question with `LLM_API_KEY` set → grounded answer or unavailable (never a 500 from a guard miss)
- [ ] Remove or invalidate the key and confirm labeled facts still answer; prose stays unavailable
- [ ] Browser network tab shows requests to the Railway API origin, not `127.0.0.1:8000`

---

## Resource and cost notes

| Item | Guidance |
| --- | --- |
| `api` memory | Prefer ≥ 1–2 GB when loading sentence-transformers; labeled-only traffic is lighter |
| `web` memory | Small; static preview |
| Disk | Corpus + Chroma in the image; no volume required if Phase 8 commits the index |
| Sleep / hobby | Free-tier sleep causes cold starts and a slow first prose embed |
| Secrets | Only `LLM_API_KEY` is sensitive; rotate in Railway if leaked |

---

## Rollback

1. In Railway, redeploy the previous successful deployment for `api` (and `web` if the UI broke).
2. Or revert the git commit that broke health / CORS / the baked API URL and push.
3. Corpus regressions: revert the ingest commit; do not hot-edit Chroma on the running container.

---

## Suggested sequence

1. Implement CORS env support and the frontend `start` script.
2. Commit a non-empty live or fixture corpus on the default branch.
3. Create Railway project → `api` + `web` → public domains → variables.
4. Pass the verification checklist.
5. Confirm Phase 8 Action → push → `api` redeploy updates `oldestAccessedAt` / `passageCount` without changing query behavior.

When that sequence is done, the assistant is reachable on Railway the same way it is in local Phase 7 acceptance: browser → FastAPI → facts / Chroma / Groq, with daily refresh still owned by GitHub Actions.
