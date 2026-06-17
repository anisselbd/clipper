"""Orchestration du pipeline complet : URL -> clips 9:16 sous-titres.

download -> transcribe -> segment -> (reframe -> captions -> render) par clip.
Ecrit un meta.json par clip et un index.json recapitulatif.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .captions import generate_ass_for_clip
from .config import Config
from .download import download
from .reframe import FaceDetector, compute_reframe
from .render import probe_resolution, render_clip
from .segment import select_segments
from .transcribe import transcribe

logger = logging.getLogger("clipper.pipeline")


def run(url: str, config: Config) -> dict:
    config.ensure_dirs()

    # 1. Telechargement
    src = download(url, config.cache_dir)

    # 2. Transcription mot a mot
    transcript = transcribe(
        src.path,
        model_size=config.whisper_model,
        language=config.lang,
        device=config.whisper_device,
        compute_type=config.whisper_compute_type,
        cache_dir=config.cache_dir,
    )
    # Trace utile pour debug / reuse.
    (config.cache_dir / f"{src.video_id}.transcript.json").write_text(
        json.dumps(transcript.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 3. Selection des moments forts (LLM, fallback heuristique)
    selected = select_segments(transcript, config)
    if not selected:
        logger.error("Aucun segment selectionne, arret.")
        return {"video": src.title, "clips": []}

    # Detecteur de visage partage entre tous les clips (chargement unique).
    detector = FaceDetector(config.models_dir, min_confidence=config.face_confidence)
    words = transcript.all_words()

    clips_meta: list[dict] = []
    for i, seg in enumerate(selected):
        clip_id = f"clip_{i:02d}"
        clip_dir = config.output_dir / clip_id
        clip_dir.mkdir(parents=True, exist_ok=True)
        logger.info("=== %s : %.1f-%.1fs | %s ===", clip_id, seg.start, seg.end, seg.title)

        try:
            # 5. Recadrage
            plan = compute_reframe(
                src.path,
                seg.start,
                seg.end,
                models_dir=config.models_dir,
                detector=detector,
                scene_threshold=config.scene_threshold,
                samples_per_scene=config.samples_per_scene,
                per_scene=config.per_scene_reframe,
            )

            # 6. Sous-titres ASS
            ass_content = generate_ass_for_clip(
                words, seg.start, seg.end, width=config.target_w, height=config.target_h
            )
            ass_path = clip_dir / "subs.ass"
            ass_path.write_text(ass_content, encoding="utf-8")

            # 7. Rendu
            out_path = clip_dir / "clip.mp4"
            render_clip(
                src.path,
                seg.start,
                seg.end,
                plan,
                ass_path,
                out_path,
                target_w=config.target_w,
                target_h=config.target_h,
                fps=config.fps,
                encoder=config.video_encoder,
                bitrate=config.video_bitrate,
            )

            res = probe_resolution(out_path)
            meta = {
                "clip_id": clip_id,
                "title": seg.title,
                "hook_score": seg.hook_score,
                "reason": seg.reason,
                "selection_source": seg.source,
                "source_url": src.url,
                "source_title": src.title,
                "start": seg.start,
                "end": seg.end,
                "duration": round(seg.end - seg.start, 2),
                "width": res[0] if res else None,
                "height": res[1] if res else None,
                "scenes": len(plan.scenes),
                "file": str(out_path.relative_to(config.output_dir)),
            }
            (clip_dir / "meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            clips_meta.append(meta)
            logger.info("%s OK -> %sx%s", clip_id, meta["width"], meta["height"])
        except Exception as exc:
            logger.exception("Echec du clip %s : %s", clip_id, exc)

    index = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_url": src.url,
        "source_title": src.title,
        "source_duration": src.duration,
        "language": transcript.language,
        "clip_count": len(clips_meta),
        "clips": clips_meta,
    }
    (config.output_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Termine : %d clip(s) dans %s", len(clips_meta), config.output_dir)
    return index
