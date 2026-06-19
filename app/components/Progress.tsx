"use client";

import type { ProgressDetail } from "@/lib/api";

const STEPS: { key: string; label: string }[] = [
  { key: "downloading", label: "Telechargement" },
  { key: "transcribing", label: "Transcription" },
  { key: "selecting", label: "Selection" },
  { key: "reframing", label: "Recadrage" },
  { key: "captioning", label: "Sous-titres" },
  { key: "rendering", label: "Rendu" },
];

function fmtBytes(n?: number): string {
  if (!n || n <= 0) return "0 Mo";
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)} Go`;
  return `${(n / 1e6).toFixed(1)} Mo`;
}

function fmtSpeed(bps?: number): string {
  if (!bps || bps <= 0) return "";
  if (bps >= 1e6) return `${(bps / 1e6).toFixed(1)} Mo/s`;
  return `${Math.round(bps / 1e3)} Ko/s`;
}

function fmtClock(s?: number): string {
  if (s == null || s < 0 || !isFinite(s)) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

/** Ligne de detail specifique a l'etape en cours (octets, vitesse, temps...). */
function detailLine(detail?: ProgressDetail | null): string {
  if (!detail) return "";
  switch (detail.kind) {
    case "download": {
      const parts = [`${fmtBytes(detail.downloaded)} / ${fmtBytes(detail.total)}`];
      const sp = fmtSpeed(detail.speed);
      if (sp) parts.push(sp);
      if (detail.eta && detail.eta > 0) parts.push(`reste ${fmtClock(detail.eta)}`);
      return parts.join("  ·  ");
    }
    case "transcribe":
      return `${fmtClock(detail.done_s)} / ${fmtClock(detail.total_s)} d'audio transcrit`;
    case "select":
      return `Analyse du transcript  ·  partie ${detail.window}/${detail.windows}`;
    case "render": {
      const t = detail.title ? `  ·  ${detail.title}` : "";
      return `Clip ${detail.clip}/${detail.clips}${t}`;
    }
    default:
      return "";
  }
}

export default function Progress({
  step,
  progress,
  message,
  detail,
}: {
  step: string;
  progress: number;
  message: string;
  detail?: ProgressDetail | null;
}) {
  const activeIndex = STEPS.findIndex((s) => s.key === step);
  const pct = Math.round(progress * 100);
  const sub = detailLine(detail);

  return (
    <div className="glass rounded-3xl p-6 sm:p-8 fade-up">
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2.5">
          <span className="w-2.5 h-2.5 rounded-full bg-[var(--accent)] dot-pulse" />
          <span className="text-[15px] font-medium">
            {message || "Traitement en cours"}
          </span>
        </div>
        <span className="text-sm text-[var(--muted)] tabular-nums">{pct}%</span>
      </div>

      <div className="h-4 mb-3.5 pl-5">
        <span className="text-[12px] text-[var(--muted)] tabular-nums">{sub || " "}</span>
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
