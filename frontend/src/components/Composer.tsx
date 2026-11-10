import type { FormEvent } from "react";

import type { SchemeSummary } from "../api";

export type SuggestionChip = {
  id: string;
  label: string;
  question: string;
  kind: "scheme" | "topic";
};

type ComposerProps = {
  value: string;
  loading: boolean;
  schemes: SchemeSummary[];
  activeSchemeId: string | null;
  onChange: (value: string) => void;
  onSubmit: (question: string) => void;
  onChip: (chip: SuggestionChip) => void;
};

const TOPIC_CHIPS: SuggestionChip[] = [
  {
    id: "expense-ratio",
    label: "Expense ratio",
    question: "What is the expense ratio?",
    kind: "topic",
  },
  {
    id: "exit-load",
    label: "Exit load",
    question: "What is the exit load?",
    kind: "topic",
  },
  {
    id: "minimum-sip",
    label: "Minimum SIP",
    question: "What is the minimum SIP?",
    kind: "topic",
  },
  {
    id: "statement-download",
    label: "Download capital gains statement",
    question: "How do I download a capital gains statement?",
    kind: "topic",
  },
];

function shortSchemeLabel(name: string): string {
  return name
    .replace(/ Fund Direct Growth$/i, "")
    .replace(/ Direct Growth$/i, "")
    .replace(/ Fund$/i, "");
}

export function buildSchemeChips(schemes: SchemeSummary[]): SuggestionChip[] {
  return schemes.map((scheme) => {
    const short = shortSchemeLabel(scheme.name);
    return {
      id: scheme.scheme_id,
      label: short,
      question: `What is the expense ratio of ${scheme.name}?`,
      kind: "scheme" as const,
    };
  });
}

export function Composer({
  value,
  loading,
  schemes,
  activeSchemeId,
  onChange,
  onSubmit,
  onChip,
}: ComposerProps) {
  const schemeChips = buildSchemeChips(schemes);
  const canSend = value.trim().length > 0 && !loading;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const question = value.trim();
    if (!question || loading) {
      return;
    }
    onSubmit(question);
  }

  return (
    <div className="sticky bottom-2 w-full pt-space-xs z-30">
      <div className="bg-surface-container-low/95 backdrop-blur-xl rounded-xl p-space-sm shadow-xl flex flex-col gap-space-sm">
        <div
          className={`flex flex-col gap-space-xs transition-opacity ${
            loading ? "opacity-40 pointer-events-none select-none" : ""
          }`}
        >
          <div className="flex items-center gap-space-xs overflow-x-auto pb-0.5">
            <span className="font-label-sm text-on-surface-variant/80 uppercase tracking-wider shrink-0 mr-1">
              Schemes
            </span>
            {schemeChips.map((chip) => {
              const active = chip.id === activeSchemeId;
              return (
                <button
                  key={chip.id}
                  className={`inline-flex items-center gap-1.5 px-space-sm py-1 rounded-full font-label-sm transition-colors shrink-0 ${
                    active
                      ? "bg-primary/10 text-primary font-medium"
                      : "bg-surface-container hover:bg-surface-container-high text-on-surface-variant hover:text-on-surface"
                  }`}
                  disabled={loading}
                  onClick={() => onChip(chip)}
                  type="button"
                >
                  {active ? (
                    <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
                  ) : null}
                  {chip.label}
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-space-xs overflow-x-auto pb-0.5">
            <span className="font-label-sm text-on-surface-variant/80 uppercase tracking-wider shrink-0 mr-1">
              Quick topics
            </span>
            {TOPIC_CHIPS.map((chip) => (
              <button
                key={chip.id}
                className="px-space-sm py-0.5 rounded-md bg-surface-container hover:bg-surface-container-high text-on-surface hover:text-primary font-label-sm transition-colors shrink-0"
                disabled={loading}
                onClick={() => onChip(chip)}
                type="button"
              >
                {chip.label}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-between text-on-surface-variant px-space-xs">
            <div className="flex items-center gap-space-xs font-label-sm text-secondary">
              <span className="material-symbols-outlined text-[14px] animate-spin">
                hourglass_top
              </span>
              <span>Fetching facts from verified scheme sources…</span>
            </div>
            <span className="font-label-sm text-on-surface-variant/50 font-mono">
              1 request pending
            </span>
          </div>
        ) : null}

        <form className="flex items-center gap-space-sm w-full" onSubmit={handleSubmit}>
          <div className="relative flex-1 flex items-center">
            <span className="material-symbols-outlined text-on-surface-variant absolute left-space-sm text-[20px]">
              search
            </span>
            <input
              autoComplete="off"
              className="w-full bg-surface-container text-on-surface placeholder:text-on-surface-variant/60 font-body-md rounded-lg pl-10 pr-space-md py-2.5 outline-none focus:bg-surface-container-high focus:ring-1 focus:ring-primary transition-colors disabled:cursor-not-allowed disabled:opacity-70"
              disabled={loading}
              onChange={(event) => onChange(event.target.value)}
              placeholder="Ask about expense ratio, exit load, SIP minimum…"
              type="text"
              value={value}
            />
          </div>
          <button
            aria-label="Send query"
            className={`h-10 px-space-md rounded-lg font-label-md flex items-center justify-center gap-space-xs transition-colors shrink-0 shadow-md ${
              canSend
                ? "bg-primary hover:bg-primary-container text-on-primary"
                : "bg-surface-container-highest text-outline cursor-not-allowed"
            }`}
            disabled={!canSend}
            type="submit"
          >
            {loading ? (
              <span className="material-symbols-outlined text-[18px] animate-spin">
                progress_activity
              </span>
            ) : (
              <>
                <span className="hidden sm:inline font-medium">Query Facts</span>
                <span className="material-symbols-outlined text-[18px]">send</span>
              </>
            )}
          </button>
        </form>

        <div className="flex items-center justify-between px-space-xs text-on-surface-variant/70 font-label-sm">
          <div className="flex items-center gap-space-xs min-w-0">
            <span className="material-symbols-outlined text-[14px] text-tertiary shrink-0">
              lock
            </span>
            <span className="truncate">
              Do not enter PAN, Aadhaar, OTP, or account numbers. Fund Facts
              answers only verifiable scheme facts.
            </span>
          </div>
          <span className="hidden md:inline font-mono text-[10px] shrink-0">
            Facts-only engine
          </span>
        </div>
      </div>
    </div>
  );
}
