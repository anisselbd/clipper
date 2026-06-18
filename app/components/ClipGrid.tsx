"use client";

import type { Clip } from "@/lib/api";
import ClipCard from "./ClipCard";

export default function ClipGrid({
  clips,
  running,
  onReveal,
  onReset,
}: {
  clips: Clip[];
  running: boolean;
  onReveal: () => void;
  onReset: () => void;
}) {
  return (
    <div className="fade-up">
      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <h2 className="text-lg font-semibold">
          {clips.length} clip{clips.length > 1 ? "s" : ""}
          {running && <span className="text-[var(--muted)] text-sm font-normal"> · generation en cours…</span>}
        </h2>
        <div className="flex gap-2.5">
          <button
            type="button"
            onClick={onReveal}
            className="text-[13px] font-medium rounded-xl px-3.5 py-2 border border-[var(--border)] hover:bg-white/5 transition-colors"
          >
            Ouvrir le dossier
          </button>
          <button
            type="button"
            onClick={onReset}
            disabled={running}
            className="btn-primary text-[13px] font-medium rounded-xl px-3.5 py-2 disabled:opacity-50"
          >
            Nouvelle video
          </button>
        </div>
      </div>

      {clips.length === 0 ? (
        <div className="glass rounded-2xl p-10 text-center text-[var(--muted)] text-sm">
          Les clips apparaitront ici au fur et a mesure.
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {clips.map((c) => (
            <ClipCard key={c.id} clip={c} />
          ))}
        </div>
      )}
    </div>
  );
}
