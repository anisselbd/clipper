"use client";

import type { Clip } from "@/lib/api";

export default function ClipCard({ clip }: { clip: Clip }) {
  return (
    <div className="glass rounded-2xl overflow-hidden fade-up flex flex-col">
      <div className="relative bg-black aspect-[9/16]">
        {clip.url ? (
          <video
            className="w-full h-full object-contain"
            src={clip.url}
            poster={clip.thumb_url ?? undefined}
            controls
            preload="metadata"
            playsInline
            aria-label={clip.title ? `Clip : ${clip.title}` : "Clip video"}
          >
            {/* Les sous-titres sont incrustes dans la video (burn-in). */}
            <track kind="captions" label="Sous-titres incrustes" />
          </video>
        ) : (
          <div className="w-full h-full grid place-items-center text-[var(--muted)] text-sm">
            indisponible
          </div>
        )}
        {typeof clip.hook_score === "number" && (
          <span
            className="absolute top-2.5 right-2.5 px-2 py-0.5 rounded-full text-[11px] font-semibold"
            style={{ background: "rgba(0,0,0,0.6)", color: "var(--gold)", backdropFilter: "blur(6px)" }}
          >
            {clip.hook_score}
          </span>
        )}
      </div>

      <div className="p-3.5 flex flex-col gap-2 flex-1">
        <p className="text-sm font-medium leading-snug line-clamp-2">
          {clip.title || clip.clip_id}
        </p>
        <div className="flex items-center gap-2 text-[11px] text-[var(--muted)]">
          {clip.duration != null && <span>{clip.duration.toFixed(0)}s</span>}
          <span>·</span>
          <span>{clip.width}x{clip.height}</span>
          {clip.selection_source && (
            <>
              <span>·</span>
              <span>{clip.selection_source === "llm" ? "LLM" : "heuristique"}</span>
            </>
          )}
        </div>
        {clip.url && (
          <a
            href={clip.url}
            download={`${clip.clip_id}.mp4`}
            className="mt-auto text-center text-[13px] font-medium rounded-xl py-2 border border-[var(--border)] hover:bg-white/5 transition-colors"
          >
            Telecharger
          </a>
        )}
      </div>
    </div>
  );
}
