# Single Railway service: build the React UI, then serve it from FastAPI.

FROM node:22-bookworm AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Empty base → browser calls /api on the same Railway domain.
ENV VITE_API_BASE_URL=
RUN npm run build

FROM python:3.11-slim
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY --from=frontend /frontend/dist /app/frontend_dist

ENV FRONTEND_DIST=/app/frontend_dist
ENV FACTS_PATH=data/scheme_facts.json
ENV CHROMA_PATH=data/chroma
ENV EMBEDDING_MODEL=BAAI/bge-small-en-v1.5

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
