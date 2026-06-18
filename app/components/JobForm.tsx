"use client";

import { useState } from "react";
import type { CreateJobInput, Preflight } from "@/lib/api";

const WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3"];
const REFRAMES = [
  { v: "auto", label: "Auto (par scene)" },
  { v: "face", label: "Visage (talking-head)" },
  { v: "motion", label: "Mouvement (sport/action)" },
  { v: "center", label: "Centre" },
];
const LANGS = [
  { code: "fr", label: "Francais" },
  { code: "en", label: "Anglais" },
  { code: "es", label: "Espagnol" },
  { code: "de", label: "Allemand" },
];

export default function JobForm({
  onSubmit,
  disabled,
  health,
}: {
  onSubmit: (input: CreateJobInput) => void;
  disabled: boolean;
  health: Preflight | null;
}) {
  const [url, setUrl] = useState("");
  const [numClips, setNumClips] = useState(5);
  const [lang, setLang] = useState("fr");
  const [whisper, setWhisper] = useState("small");
  const [reframe, setReframe] = useState("auto");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    onSubmit({ url: url.trim(), num_clips: numClips, lang, whisper_model: whisper, reframe_mode: reframe });
  };

  return (
    <form onSubmit={submit} className="glass rounded-3xl p-6 sm:p-8 fade-up">
      <label htmlFor="url" className="block text-sm text-[var(--muted)] mb-2">
        URL de la video
      </label>
      <input
        id="url"
        className="field w-full rounded-2xl px-4 py-3.5 text-[15px] mb-5"
        placeholder="https://www.youtube.com/watch?v=..."
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        disabled={disabled}
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div>
          <label htmlFor="numClips" className="block text-xs text-[var(--muted)] mb-1.5">
            Nombre de clips
          </label>
          <input
            id="numClips"
            type="number"
            min={1}
            max={20}
            className="field w-full rounded-xl px-3 py-2.5 text-sm"
            value={numClips}
            onChange={(e) => setNumClips(Number(e.target.value))}
            disabled={disabled}
          />
        </div>
        <div>
          <label htmlFor="lang" className="block text-xs text-[var(--muted)] mb-1.5">
            Langue
          </label>
          <select
            id="lang"
            className="field w-full rounded-xl px-3 py-2.5 text-sm"
            value={lang}
            onChange={(e) => setLang(e.target.value)}
            disabled={disabled}
          >
            {LANGS.map((l) => (
              <option key={l.code} value={l.code}>
                {l.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="whisper" className="block text-xs text-[var(--muted)] mb-1.5">
            Modele Whisper
          </label>
          <select
            id="whisper"
            className="field w-full rounded-xl px-3 py-2.5 text-sm"
            value={whisper}
            onChange={(e) => setWhisper(e.target.value)}
            disabled={disabled}
          >
            {WHISPER_MODELS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="reframe" className="block text-xs text-[var(--muted)] mb-1.5">
            Recadrage
          </label>
          <select
            id="reframe"
            className="field w-full rounded-xl px-3 py-2.5 text-sm"
            value={reframe}
            onChange={(e) => setReframe(e.target.value)}
            disabled={disabled}
          >
            {REFRAMES.map((r) => (
              <option key={r.v} value={r.v}>
                {r.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <button
        type="submit"
        disabled={disabled || !url.trim()}
        className="btn-primary w-full rounded-2xl py-3.5 font-semibold text-[15px]"
      >
        Generer les clips
      </button>

      {health && (
        <div className="mt-5 flex flex-wrap gap-2 text-[11px]">
          <Badge label={`Selection : ${health.selection_backend === "llm" ? "LLM" : "heuristique"}`} on={health.selection_backend === "llm"} />
          <Badge label={`Sous-titres : ${health.subtitle_backend}`} />
          <Badge label={`Encodeur : ${health.video_encoder}`} />
          <Badge label={`Visage : ${health.face_backend}`} />
        </div>
      )}
    </form>
  );
}

function Badge({ label, on }: { label: string; on?: boolean }) {
  return (
    <span
      className="px-2.5 py-1 rounded-full border"
      style={{
        borderColor: "var(--border)",
        background: on ? "rgba(91,140,255,0.14)" : "rgba(255,255,255,0.03)",
        color: on ? "#a9c2ff" : "var(--muted)",
      }}
    >
      {label}
    </span>
  );
}
