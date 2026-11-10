import { useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  getHealth,
  getSchemes,
  postQuery,
  type HealthResponse,
  type SchemeSummary,
} from "./api";
import { Composer, type SuggestionChip } from "./components/Composer";
import { Disclaimer } from "./components/Disclaimer";
import { Transcript, type TranscriptTurn } from "./components/Transcript";

function BrandMark({ size = "md" }: { size?: "sm" | "md" }) {
  const box = size === "sm" ? "h-8 w-8 rounded-lg" : "w-14 h-14 rounded-xl p-2.5";
  const icon = size === "sm" ? "text-[18px]" : "text-[28px]";
  return (
    <div
      className={`${box} bg-surface-container-high flex items-center justify-center shadow-md shrink-0`}
    >
      <span className={`material-symbols-outlined text-primary ${icon}`}>analytics</span>
    </div>
  );
}

function formatTime(date = new Date()): string {
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function nextPriorSchemeId(
  current: string | null,
  responseType: string,
  schemeId: string | null | undefined,
): string | null {
  if (responseType === "refusal") {
    return null;
  }
  if (responseType === "unavailable" && !schemeId) {
    return null;
  }
  if (responseType === "factual" && schemeId) {
    return schemeId;
  }
  // Keep scheme context after an unavailable reply that still names a scheme.
  if (responseType === "unavailable" && schemeId) {
    return schemeId;
  }
  return current;
}

function EmptyState({
  schemes,
  onStage,
}: {
  schemes: SchemeSummary[];
  onStage: (question: string) => void;
}) {
  return (
    <div className="flex flex-col w-full py-space-md">
      <div className="flex items-center justify-between gap-space-sm mb-space-md text-on-surface-variant font-label-sm">
        <div className="flex items-center gap-space-xs bg-surface-container-low px-space-sm py-1 rounded-lg">
          <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
          <span className="text-on-surface">{schemes.length || 5} SCHEMES GROUNDED</span>
          <span className="text-outline">·</span>
          <span>FACTS & PASSAGES INDEXED</span>
        </div>
      </div>

      <section className="relative bg-surface-container-low rounded-xl p-space-lg sm:p-space-xl overflow-hidden shadow-xl">
        <div className="absolute -top-24 -right-24 w-72 h-72 rounded-full bg-primary/5 blur-3xl pointer-events-none" />
        <div className="absolute -bottom-24 -left-24 w-72 h-72 rounded-full bg-secondary/5 blur-3xl pointer-events-none" />
        <div className="relative z-10 flex flex-col items-center text-center max-w-2xl mx-auto">
          <div className="relative mb-space-md">
            <BrandMark size="md" />
            <div className="absolute -bottom-1 -right-1 w-5 h-5 rounded-full bg-primary flex items-center justify-center shadow-sm">
              <span className="material-symbols-outlined text-[13px] text-on-primary font-bold">
                verified
              </span>
            </div>
          </div>
          <h1 className="font-headline-lg sm:font-headline-xl text-on-surface tracking-tight">
            Ask a factual question about one of the five HDFC schemes
          </h1>
          <p className="font-body-md text-on-surface-variant mt-space-sm max-w-xl">
            Fund Facts answers from indexed scheme facts and passages only. It does
            not recommend schemes or forecast returns.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-space-xs w-full mt-space-lg text-left">
            {[
              "Verifiable expense ratios & exit loads",
              "Minimum SIP & lump-sum rules",
              "Riskometer, benchmark, and tax notes",
              "No buy/sell advice or return forecasts",
            ].map((item, index) => (
              <div
                key={item}
                className="flex items-center gap-space-xs bg-surface-container px-space-md py-space-xs rounded-lg"
              >
                <span
                  className={`material-symbols-outlined text-[16px] shrink-0 ${
                    index === 3 ? "text-error" : "text-primary"
                  }`}
                >
                  {index === 3 ? "block" : "check_circle"}
                </span>
                <span
                  className={`font-label-sm ${
                    index === 3 ? "text-on-surface-variant" : "text-on-surface"
                  }`}
                >
                  {item}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {schemes.length > 0 ? (
        <section className="mt-space-lg">
          <div className="flex items-center justify-between mb-space-sm px-1">
            <div className="flex items-center gap-space-xs">
              <span className="font-label-md uppercase tracking-wider text-on-surface font-semibold">
                Active fund coverage
              </span>
              <span className="px-1.5 py-0.5 rounded-sm bg-surface-container-high font-label-sm text-primary">
                {schemes.length} OF 5
              </span>
            </div>
            <span className="font-label-sm text-on-surface-variant">
              Click to stage a question
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-space-sm">
            {schemes.map((scheme) => (
              <button
                key={scheme.scheme_id}
                className="group relative text-left bg-surface-container-low hover:bg-surface-container p-space-md rounded-xl transition-all duration-200 flex flex-col justify-between shadow-sm hover:shadow-md"
                onClick={() =>
                  onStage(`What is the expense ratio of ${scheme.name}?`)
                }
                type="button"
              >
                <div>
                  <h2 className="font-headline-md font-medium text-on-surface group-hover:text-primary transition-colors line-clamp-2">
                    {scheme.name}
                  </h2>
                  <p className="font-body-sm text-on-surface-variant mt-1 truncate">
                    {scheme.url.replace("https://", "")}
                  </p>
                </div>
                <div className="flex items-center justify-between pt-space-md mt-space-sm">
                  <span className="font-label-sm text-outline group-hover:text-on-surface transition-colors">
                    Scheme facts
                  </span>
                  <span className="font-label-md text-primary group-hover:translate-x-0.5 transition-transform">
                    Ask facts ↗
                  </span>
                </div>
              </button>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [schemes, setSchemes] = useState<SchemeSummary[]>([]);
  const [draft, setDraft] = useState("");
  const [turns, setTurns] = useState<TranscriptTurn[]>([]);
  const [loading, setLoading] = useState(false);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [priorSchemeId, setPriorSchemeId] = useState<string | null>(null);
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const streamEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function bootstrap() {
      try {
        const [healthResponse, schemeResponse] = await Promise.all([
          getHealth(),
          getSchemes(),
        ]);
        if (cancelled) {
          return;
        }
        setHealth(healthResponse);
        setSchemes(schemeResponse);
        setBootstrapError(null);
      } catch (error) {
        if (cancelled) {
          return;
        }
        const message =
          error instanceof ApiError
            ? error.detail
            : "Could not reach the API. Start the FastAPI server and refresh.";
        setBootstrapError(message);
      }
    }
    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    streamEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, loading, pendingQuestion]);

  const showEmpty = turns.length === 0 && !loading;

  const activeSchemeId = useMemo(() => priorSchemeId, [priorSchemeId]);

  async function ask(question: string) {
    const trimmed = question.trim();
    if (!trimmed || loading) {
      return;
    }

    setValidationError(null);
    setLoading(true);
    setPendingQuestion(trimmed);
    setDraft("");

    try {
      const response = await postQuery(trimmed, priorSchemeId);
      const turn: TranscriptTurn = {
        id: crypto.randomUUID(),
        question: trimmed,
        askedAt: formatTime(),
        response,
      };
      setTurns((current) => [...current, turn]);
      setPriorSchemeId(
        nextPriorSchemeId(priorSchemeId, response.responseType, response.scheme?.id),
      );
    } catch (error) {
      if (error instanceof ApiError && error.status === 422) {
        setValidationError(error.detail);
        setDraft(trimmed);
      } else {
        const message =
          error instanceof ApiError
            ? error.detail
            : "Network error. Check that the API is running, then retry.";
        setTurns((current) => [
          ...current,
          {
            id: crypto.randomUUID(),
            question: trimmed,
            askedAt: formatTime(),
            error: message,
          },
        ]);
      }
    } finally {
      setLoading(false);
      setPendingQuestion(null);
    }
  }

  function handleChip(chip: SuggestionChip) {
    setDraft(chip.question);
    setValidationError(null);
  }

  function resetChat() {
    if (loading) {
      return;
    }
    setTurns([]);
    setPriorSchemeId(null);
    setDraft("");
    setValidationError(null);
    setPendingQuestion(null);
  }

  return (
    <div className="bg-surface text-on-surface min-h-screen flex flex-col antialiased">
      <header className="fixed top-0 left-0 right-0 w-full z-50 bg-surface/90 backdrop-blur-xl shadow-[0_1px_8px_rgba(0,0,0,0.4)]">
        <div className="h-16 w-full px-margin md:px-margin-desktop flex items-center justify-between gap-space-md">
          <div className="flex items-center gap-space-md min-w-0">
            <BrandMark size="sm" />
            <div className="flex flex-col min-w-0">
              <div className="flex items-center gap-space-sm">
                <span className="font-headline-md font-semibold tracking-tight text-on-surface leading-tight">
                  Fund Facts
                </span>
                {health?.oldestAccessedAt ? (
                  <span className="hidden sm:inline-flex items-center gap-space-xs px-space-sm py-0.5 rounded-full bg-surface-container-high text-primary font-label-sm border border-outline-variant/40">
                    <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
                    Sources last captured:{" "}
                    {new Date(`${health.oldestAccessedAt}T00:00:00Z`).toLocaleDateString(
                      "en-GB",
                      {
                        day: "numeric",
                        month: "short",
                        year: "numeric",
                        timeZone: "UTC",
                      },
                    )}
                  </span>
                ) : null}
              </div>
              <span className="font-body-sm text-on-surface-variant truncate">
                Public scheme facts · Not investment advice
              </span>
            </div>
          </div>
          <div className="flex items-center gap-space-md shrink-0">
            <button
              className="flex items-center gap-space-xs px-space-sm py-space-xs rounded-lg bg-surface-container-low hover:bg-surface-container text-on-surface-variant hover:text-on-surface transition-colors font-label-sm disabled:opacity-40"
              disabled={loading || turns.length === 0}
              onClick={resetChat}
              title="Clear conversation"
              type="button"
            >
              <span className="material-symbols-outlined text-[16px]">restart_alt</span>
              <span className="hidden lg:inline">Reset Chat</span>
            </button>
          </div>
        </div>
        <Disclaimer
          oldestAccessedAt={health?.oldestAccessedAt ?? null}
          schemeCount={schemes.length || health?.schemeCount || 5}
          variant="banner"
        />
      </header>

      <main className="w-full pt-[7.5rem] bg-surface flex-1">
        <div className="max-w-[920px] mx-auto px-margin w-full pb-40">
          {bootstrapError ? (
            <div className="mb-space-lg rounded-xl bg-error-container/30 border border-error/40 px-space-md py-space-sm text-on-error-container font-body-md">
              {bootstrapError}
            </div>
          ) : null}

          {!showEmpty ? (
            <Disclaimer
              oldestAccessedAt={health?.oldestAccessedAt ?? null}
              schemeCount={schemes.length || health?.schemeCount || 5}
              variant="panel"
            />
          ) : null}

          {showEmpty ? (
            <EmptyState onStage={setDraft} schemes={schemes} />
          ) : (
            <Transcript
              loading={loading}
              onSchemePick={(_name, question) => {
                setDraft(question);
              }}
              pendingQuestion={pendingQuestion}
              schemes={schemes}
              turns={turns}
            />
          )}

          {validationError ? (
            <div className="mt-space-md rounded-lg bg-tertiary/10 border border-tertiary/30 px-space-md py-space-sm text-tertiary font-body-sm">
              {validationError}
            </div>
          ) : null}

          <div className="mt-space-xl" ref={streamEndRef} />

          <Composer
            activeSchemeId={activeSchemeId}
            loading={loading}
            onChange={(value) => {
              setDraft(value);
              if (validationError) {
                setValidationError(null);
              }
            }}
            onChip={handleChip}
            onSubmit={ask}
            schemes={schemes}
            value={draft}
          />
        </div>
      </main>

      <footer className="w-full bg-surface-container-lowest mt-auto py-space-md shadow-[0_-1px_4px_rgba(0,0,0,0.2)]">
        <div className="max-w-[920px] mx-auto px-margin flex flex-col sm:flex-row items-center justify-between gap-space-sm font-label-sm text-on-surface-variant">
          <span>Fund Facts · Source-grounded mutual fund facts</span>
          <div className="flex items-center gap-space-md">
            <a
              className="hover:text-on-surface transition-colors"
              href="https://www.amfiindia.com/investor"
              rel="noreferrer"
              target="_blank"
            >
              AMFI investor
            </a>
            <a
              className="hover:text-on-surface transition-colors"
              href="https://investor.sebi.gov.in/"
              rel="noreferrer"
              target="_blank"
            >
              SEBI investor
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;
