"use client";

const STEPS: { key: string; label: string }[] = [
  { key: "downloading", label: "Telechargement" },
  { key: "transcribing", label: "Transcription" },
  { key: "selecting", label: "Selection" },
  { key: "reframing", label: "Recadrage" },
  { key: "captioning", label: "Sous-titres" },
  { key: "rendering", label: "Rendu" },
];

export default function Progress({
  step,
  progress,
  message,
}: {
  step: string;
  progress: number;
  message: string;
}) {
  const activeIndex = STEPS.findIndex((s) => s.key === step);
  const pct = Math.round(progress * 100);

  return (
    <div className="glass rounded-3xl p-6 sm:p-8 fade-up">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <span className="w-2.5 h-2.5 rounded-full bg-[var(--accent)] dot-pulse" />
          <span className="text-[15px] font-medium">
            {message || "Traitement en cours"}
          </span>
        </div>
        <span className="text-sm text-[var(--muted)] tabular-nums">{pct}%</span>
      </div>

      <div className="h-2.5 rounded-full bg-white/5 overflow-hidden bar-shimmer mb-7">
        <div
          className="h-full rounded-full transition-[width] duration-500 ease-out"
          style={{
            width: `${Math.max(4, pct)}%`,
            background: "linear-gradient(90deg, #5b8cff, #8b5cff)",
          }}
        />
      </div>

      <ol className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {STEPS.map((s, i) => {
          const done = activeIndex > i || step === "done";
          const active = activeIndex === i && step !== "done";
          return (
            <li
              key={s.key}
              className="flex items-center gap-2.5 text-sm"
              style={{ color: done || active ? "var(--text)" : "var(--muted)" }}
            >
              <span
                className="w-5 h-5 rounded-full flex items-center justify-center text-[11px] shrink-0"
                style={{
                  background: done
                    ? "rgba(91,140,255,0.9)"
                    : active
                      ? "rgba(91,140,255,0.18)"
                      : "rgba(255,255,255,0.05)",
                  border: active ? "1px solid var(--accent)" : "1px solid var(--border)",
                }}
              >
                {done ? "✓" : i + 1}
              </span>
              {s.label}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
