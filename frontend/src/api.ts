// Dev talks to local Uvicorn. Production (same-origin Railway) uses relative /api.
const _viteApiBase = import.meta.env.VITE_API_BASE_URL as string | undefined;
const API_BASE =
  _viteApiBase !== undefined && _viteApiBase !== null
    ? String(_viteApiBase).replace(/\/$/, "")
    : import.meta.env.DEV
      ? "http://127.0.0.1:8000"
      : "";

export type Citation = {
  url: string;
  title: string;
  authority: string;
  accessedAt: string | null;
  asOf: string | null;
};

export type SchemeRef = {
  id: string;
  name: string;
};

export type QueryResponse = {
  responseType: "factual" | "refusal" | "unavailable" | string;
  queryType: string;
  answer: string;
  scheme: SchemeRef | null;
  citations: Citation[];
};

export type SchemeSummary = {
  scheme_id: string;
  name: string;
  url: string;
};

export type HealthResponse = {
  status: string;
  factsLoaded: boolean;
  schemeCount: number;
  passageCount: number;
  embeddingModel: string;
  oldestAccessedAt: string | null;
};

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function formatDetail(payload: unknown): string {
  if (!payload || typeof payload !== "object") {
    return "Request failed.";
  }
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return null;
      })
      .filter(Boolean);
    if (messages.length > 0) {
      return messages.join(" ");
    }
  }
  return "Request failed.";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(0, "Network error. Check that the API is running, then retry.");
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status}).`;
    try {
      detail = formatDetail(await response.json());
    } catch {
      // keep default
    }
    throw new ApiError(response.status, detail);
  }

  return (await response.json()) as T;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health");
}

export function getSchemes(): Promise<SchemeSummary[]> {
  return request<SchemeSummary[]>("/api/schemes");
}

export function postQuery(
  question: string,
  priorSchemeId?: string | null,
): Promise<QueryResponse> {
  const body: { question: string; priorSchemeId?: string } = { question };
  if (priorSchemeId) {
    body.priorSchemeId = priorSchemeId;
  }
  return request<QueryResponse>("/api/query", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export { API_BASE };
