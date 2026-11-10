type DisclaimerProps = {
  oldestAccessedAt: string | null;
  schemeCount?: number;
  variant?: "banner" | "panel";
};

function formatCaptureDate(value: string | null): string | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function Disclaimer({
  oldestAccessedAt,
  schemeCount = 5,
  variant = "banner",
}: DisclaimerProps) {
  const captureLabel = formatCaptureDate(oldestAccessedAt);

  if (variant === "panel") {
    return (
      <div className="w-full bg-surface-container-low rounded-xl px-space-md py-space-sm mb-space-lg flex flex-col sm:flex-row items-start sm:items-center justify-between gap-space-sm shadow-sm">
        <div className="flex items-center gap-space-sm min-w-0">
          <span className="material-symbols-outlined text-secondary text-[20px] shrink-0">
            info
          </span>
          <div className="min-w-0">
            <p className="font-body-sm text-on-surface-variant leading-snug">
              This assistant shares public facts from HDFC scheme sources and does
              not give investment advice.
            </p>
            {captureLabel ? (
              <p className="font-label-sm text-outline mt-1">
                Sources last captured: {captureLabel}
              </p>
            ) : null}
          </div>
        </div>
        <a
          className="shrink-0 flex items-center gap-space-xs font-label-sm text-secondary hover:text-secondary-fixed transition-colors"
          href="https://www.amfiindia.com/investor"
          rel="noreferrer"
          target="_blank"
        >
          <span>SEBI / AMFI Statutory Guidelines</span>
          <span className="material-symbols-outlined text-[14px]">arrow_outward</span>
        </a>
      </div>
    );
  }

  return (
    <div className="w-full bg-surface-container-lowest/90 backdrop-blur-md px-margin md:px-margin-desktop py-space-xs flex items-center justify-center">
      <div className="max-w-[920px] w-full flex flex-col sm:flex-row items-center justify-between gap-space-sm text-center sm:text-left">
        <div className="flex items-center gap-space-xs text-on-surface-variant font-body-sm">
          <span className="material-symbols-outlined text-secondary text-[16px] shrink-0">
            info
          </span>
          <span>
            This assistant shares public facts from HDFC scheme sources and does
            not give investment advice.
          </span>
        </div>
        <div className="flex items-center gap-space-sm shrink-0">
          {captureLabel ? (
            <span className="inline-flex items-center gap-space-xs px-space-sm py-0.5 rounded-full bg-surface-container-high text-primary font-label-sm border border-outline-variant/40">
              <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
              Sources last captured: {captureLabel}
            </span>
          ) : null}
          <span className="font-label-sm text-outline hidden sm:inline">
            {schemeCount} schemes grounded
          </span>
        </div>
      </div>
    </div>
  );
}
