import type { Citation, QueryResponse, SchemeSummary } from "../api";

export type TranscriptTurn = {
  id: string;
  question: string;
  askedAt: string;
  response?: QueryResponse;
  error?: string;
};

type TranscriptProps = {
  turns: TranscriptTurn[];
  loading: boolean;
  pendingQuestion: string | null;
  schemes: SchemeSummary[];
  onSchemePick?: (schemeName: string, question: string) => void;
};

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function authorityBadge(authority: string): { label: string; className: string } {
  if (authority === "official") {
    return {
      label: "Official",
      className: "bg-secondary/10 text-secondary",
    };
  }
  return {
    label: "Platform",
    className: "bg-primary/10 text-primary",
  };
}

function accessedLabel(citations: Citation[]): string | null {
  const dates = citations
    .map((item) => item.accessedAt)
    .filter((value): value is string => Boolean(value));
  if (dates.length === 0) {
    return null;
  }
  const oldest = [...dates].sort()[0];
  const parsed = new Date(`${oldest}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) {
    return oldest;
  }
  return parsed.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

function isClarification(response: QueryResponse, schemes: SchemeSummary[]): boolean {
  if (response.responseType !== "unavailable" || response.scheme) {
    return false;
  }
  return schemes.every((scheme) => response.answer.includes(scheme.name));
}

function UserBubble({ question, askedAt }: { question: string; askedAt: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[480px] bg-surface-container-high rounded-xl rounded-tr-xs px-space-md py-space-sm shadow-sm">
        <p className="font-body-md text-on-surface">{question}</p>
        <div className="flex justify-end mt-1">
          <span className="font-label-sm text-on-surface-variant/70">{askedAt}</span>
        </div>
      </div>
    </div>
  );
}

function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return null;
  }

  const updated = accessedLabel(citations);

  return (
    <div className="mt-space-xs bg-surface-container rounded-lg p-space-sm flex flex-col gap-space-xs">
      <div className="flex items-center justify-between">
        <span className="font-label-sm text-on-surface-variant font-medium tracking-wide uppercase">
          Verified sources ({citations.length})
        </span>
      </div>
      {citations.map((citation) => {
        const badge = authorityBadge(citation.authority);
        return (
          <div
            key={`${citation.url}-${citation.title}`}
            className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 p-space-xs rounded bg-surface-container-low hover:bg-surface-container-high transition-colors"
          >
            <div className="flex items-center gap-space-xs min-w-0">
              <span className="material-symbols-outlined text-secondary text-[16px] shrink-0">
                article
              </span>
              <span className="font-body-sm text-on-surface truncate">
                {citation.title}
              </span>
            </div>
            <div className="flex items-center gap-space-sm shrink-0">
              <span className={`px-space-xs py-0.5 rounded font-label-sm ${badge.className}`}>
                {badge.label}
              </span>
              <a
                className="text-secondary hover:text-secondary-fixed font-label-sm flex items-center gap-0.5"
                href={citation.url}
                rel="noreferrer"
                target="_blank"
              >
                <span>{hostname(citation.url)}</span>
                <span className="material-symbols-outlined text-[12px]">launch</span>
              </a>
            </div>
          </div>
        );
      })}
      {updated ? (
        <div className="flex items-center gap-space-xs pt-1 text-on-surface-variant/70 font-label-sm">
          <span className="material-symbols-outlined text-[14px]">schedule</span>
          <span>Last updated from sources: {updated}</span>
        </div>
      ) : null}
    </div>
  );
}

function FactualMessage({ response }: { response: QueryResponse }) {
  return (
    <div className="flex items-start gap-space-md max-w-full">
      <div className="w-7 h-7 rounded-lg bg-surface-container flex items-center justify-center shrink-0 mt-0.5">
        <span className="material-symbols-outlined text-primary text-[18px]">verified</span>
      </div>
      <div className="flex flex-col gap-space-sm flex-1 min-w-0 bg-surface-container-low rounded-xl p-space-md shadow-sm">
        {response.scheme ? (
          <div className="flex flex-wrap items-center gap-space-xs">
            <span className="inline-flex items-center gap-1 px-space-sm py-0.5 rounded-full bg-primary/10 text-primary font-label-sm font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-primary" />
              {response.scheme.name}
            </span>
            <span className="font-label-sm text-on-surface-variant">Grounded fact</span>
          </div>
        ) : null}
        <p className="font-body-md text-on-surface leading-relaxed whitespace-pre-wrap">
          {response.answer}
        </p>
        <CitationList citations={response.citations} />
      </div>
    </div>
  );
}

function RefusalMessage({ response }: { response: QueryResponse }) {
  return (
    <div className="flex items-start gap-space-md max-w-full">
      <div className="w-7 h-7 rounded-lg bg-surface-container flex items-center justify-center shrink-0 mt-0.5">
        <span className="material-symbols-outlined text-tertiary text-[18px]">gpp_maybe</span>
      </div>
      <div className="flex flex-col gap-space-sm flex-1 min-w-0 bg-surface-container-low rounded-xl p-space-md shadow-sm">
        <div className="flex items-center gap-space-xs">
          <span className="inline-flex items-center gap-1 px-space-sm py-0.5 rounded-full bg-tertiary/15 text-tertiary font-label-sm font-medium">
            <span className="material-symbols-outlined text-[14px]">lock</span>
            Refusal · Outside factual scope
          </span>
        </div>
        <p className="font-body-md text-on-surface leading-relaxed whitespace-pre-wrap">
          {response.answer}
        </p>
        {response.citations.length > 0 ? (
          <div className="bg-surface-container rounded-lg p-space-sm flex flex-col gap-space-xs">
            <span className="font-body-sm text-on-surface-variant font-medium">
              For investor education, see:
            </span>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-space-xs mt-1">
              {response.citations.map((citation) => (
                <a
                  key={citation.url}
                  className="p-space-xs rounded bg-surface-container-low hover:bg-surface-container-high transition-colors flex flex-col justify-between"
                  href={citation.url}
                  rel="noreferrer"
                  target="_blank"
                >
                  <div className="flex items-center justify-between gap-space-xs">
                    <span className="font-label-sm text-on-surface font-medium truncate">
                      {citation.title}
                    </span>
                    <span className="material-symbols-outlined text-secondary text-[14px]">
                      arrow_outward
                    </span>
                  </div>
                  <span className="font-label-sm text-on-surface-variant truncate">
                    {hostname(citation.url)}
                  </span>
                </a>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function UnavailableMessage({
  response,
  schemes,
  onSchemePick,
}: {
  response: QueryResponse;
  schemes: SchemeSummary[];
  onSchemePick?: (schemeName: string, question: string) => void;
}) {
  const clarification = isClarification(response, schemes);

  return (
    <div className="flex items-start gap-space-md max-w-full">
      <div className="w-7 h-7 rounded-lg bg-surface-container flex items-center justify-center shrink-0 mt-0.5">
        <span className="material-symbols-outlined text-secondary text-[18px]">
          {clarification ? "help_center" : "info"}
        </span>
      </div>
      <div className="flex flex-col gap-space-sm flex-1 min-w-0 bg-surface-container-low rounded-xl p-space-md shadow-sm">
        <div className="flex items-center gap-space-xs">
          <span
            className={`inline-flex items-center gap-1 px-space-sm py-0.5 rounded-full font-label-sm ${
              clarification
                ? "bg-surface-container-high text-on-surface-variant"
                : "bg-tertiary/15 text-tertiary"
            }`}
          >
            <span className="material-symbols-outlined text-[14px]">
              {clarification ? "tune" : "warning"}
            </span>
            {clarification ? "Clarification needed" : "Unavailable in sources"}
          </span>
        </div>
        <p className="font-body-md text-on-surface leading-relaxed whitespace-pre-wrap">
          {response.answer}
        </p>
        {clarification ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-space-xs mt-1">
            {schemes.map((scheme, index) => (
              <button
                key={scheme.scheme_id}
                className="group text-left p-space-xs rounded-lg bg-surface-container hover:bg-surface-container-high transition-colors flex items-center justify-between"
                onClick={() =>
                  onSchemePick?.(
                    scheme.name,
                    `What is the expense ratio of ${scheme.name}?`,
                  )
                }
                type="button"
              >
                <div className="flex items-center gap-space-xs min-w-0">
                  <span className="font-label-sm text-primary font-mono shrink-0">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span className="font-body-sm text-on-surface truncate group-hover:text-primary transition-colors">
                    {scheme.name}
                  </span>
                </div>
                <span className="material-symbols-outlined text-[16px] text-on-surface-variant group-hover:text-primary">
                  arrow_forward
                </span>
              </button>
            ))}
          </div>
        ) : null}
        {response.scheme ? (
          <div className="flex flex-wrap items-center gap-space-xs">
            <span className="inline-flex items-center gap-1 px-space-sm py-0.5 rounded-full bg-primary/10 text-primary font-label-sm font-medium">
              {response.scheme.name}
            </span>
          </div>
        ) : null}
        <CitationList citations={response.citations} />
      </div>
    </div>
  );
}

function LoadingMessage() {
  return (
    <div className="flex items-start gap-space-md w-full">
      <div className="w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center shrink-0 shadow-sm mt-0.5 relative">
        <span className="material-symbols-outlined text-primary text-[18px]">neurology</span>
        <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-primary rounded-full animate-ping" />
      </div>
      <div className="flex-1 max-w-[85%] bg-surface-container rounded-xl p-space-md shadow-lg space-y-space-md">
        <div className="flex flex-wrap items-center justify-between gap-space-sm pb-space-xs border-b border-surface-container-highest/60">
          <span className="inline-flex items-center gap-space-xs px-space-sm py-0.5 rounded-full bg-primary/15 text-primary font-label-sm font-medium">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
            Retrieving sources…
          </span>
          <span className="font-label-sm text-secondary flex items-center gap-1 font-mono">
            <span className="material-symbols-outlined text-[14px] animate-spin">sync</span>
            Working
          </span>
        </div>
        <div className="space-y-space-sm pt-space-xs">
          <div className="h-4 bg-surface-container-highest rounded-lg w-11/12 animate-pulse" />
          <div className="h-4 bg-surface-container-highest rounded-lg w-4/5 animate-pulse" />
          <div className="h-4 bg-surface-container-highest rounded-lg w-3/5 animate-pulse" />
        </div>
      </div>
    </div>
  );
}

function ErrorMessage({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-space-md max-w-full">
      <div className="w-7 h-7 rounded-lg bg-surface-container flex items-center justify-center shrink-0 mt-0.5">
        <span className="material-symbols-outlined text-error text-[18px]">error</span>
      </div>
      <div className="flex flex-col gap-space-sm flex-1 min-w-0 bg-surface-container-low rounded-xl p-space-md shadow-sm">
        <span className="inline-flex items-center gap-1 px-space-sm py-0.5 rounded-full bg-error/15 text-error font-label-sm font-medium w-fit">
          Could not complete request
        </span>
        <p className="font-body-md text-on-surface leading-relaxed">{message}</p>
      </div>
    </div>
  );
}

export function Transcript({
  turns,
  loading,
  pendingQuestion,
  schemes,
  onSchemePick,
}: TranscriptProps) {
  return (
    <div className="flex flex-col gap-space-xl w-full" id="chat-stream">
      {turns.map((turn) => (
        <div key={turn.id} className="flex flex-col gap-space-sm">
          <UserBubble askedAt={turn.askedAt} question={turn.question} />
          {turn.error ? <ErrorMessage message={turn.error} /> : null}
          {turn.response?.responseType === "factual" ? (
            <FactualMessage response={turn.response} />
          ) : null}
          {turn.response?.responseType === "refusal" ? (
            <RefusalMessage response={turn.response} />
          ) : null}
          {turn.response?.responseType === "unavailable" ? (
            <UnavailableMessage
              onSchemePick={onSchemePick}
              response={turn.response}
              schemes={schemes}
            />
          ) : null}
          {turn.response &&
          !["factual", "refusal", "unavailable"].includes(turn.response.responseType) ? (
            <FactualMessage response={turn.response} />
          ) : null}
        </div>
      ))}

      {loading && pendingQuestion ? (
        <div className="flex flex-col gap-space-sm">
          <UserBubble
            askedAt="Now"
            question={pendingQuestion}
          />
          <LoadingMessage />
        </div>
      ) : null}
    </div>
  );
}
