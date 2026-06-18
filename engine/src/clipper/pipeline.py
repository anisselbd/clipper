"""Orchestration du pipeline complet : URL -> clips 9:16 sous-titres.

download -> transcribe -> segment -> (reframe -> captions -> render) par clip.
Ecrit un meta.json par clip et un index.json recapitulatif.

Le moteur est enveloppe par des providers (encoder, llm) et un rapport preflight
injectables. Un callback de progression (on_progress) et de clip (on_clip)
permettent a l'API de suivre l'avancement et d'afficher les clips au fil de l'eau.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from .captions import generate_ass_for_clip, render_overlay_assets
from .config import Config
from .download import download
from .preflight import PreflightReport, run_preflight
from .providers.encoder import LocalEncoder
from .providers.encoder.base import EncoderProvider
from .providers.llm import LocalLLMProvider
from .providers.llm.base import LLMProvider
from .reframe import FaceDetector, compute_reframe
from .render import probe_resolution
from .transcribe import transcribe

logger = logging.getLogger("clipper.pipeline")

ProgressFn = Callable[[str, float, str], None]
ClipFn = Callable[[dict], None]


def _make_thumbnail(clip_path: Path, out_path: Path, at: float) -> bool:
    """Extrait une vignette JPEG du clip rendu."""
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{at:.2f}", "-i", str(clip_path),
        "-frames:v", "1", "-vf", "scale=360:-1", str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode == 0 and out_path.exists()


def run(
    url: str,
    config: Config,
    *,
    on_progress: ProgressFn | None = None,
    on_clip: ClipFn | None = None,
    report: PreflightReport | None = None,
    encoder: EncoderProvider | None = None,
    llm: LLMProvider | None = None,
) -> dict:
    config.ensure_dirs()
    report = report or run_preflight(config)
    encoder = encoder or LocalEncoder.from_report(report)
    llm = llm or LocalLLMProvider()

    def emit(step: str, progress: float, message: str = "") -> None:
        if on_progress is not None:
            try:
                on_progress(step, round(progress, 3), message)
            except Exception:  # un abonne SSE casse ne doit pas tuer le pipeline
                logger.debug("on_progress a leve une exception", exc_info=True)

    # 1. Telechargement
    emit("downloading", 0.02, "Telechargement de la video")
    src = download(url, config.cache_dir)
    emit("downloading", 0.10, src.title)

    # 2. Transcription mot a mot
    emit("transcribing", 0.15, "Transcription mot a mot")
    transcript = transcribe(
        src.path,
        model_size=config.whisper_model,
        language=config.lang,
        device=config.whisper_device,
        compute_type=config.whisper_compute_type,
        cache_dir=config.cache_dir,
    )
    (config.cache_dir / f"{src.video_id}.transcript.json").write_text(
        json.dumps(transcript.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    emit("transcribing", 0.45, f"{len(transcript.segments)} segments")

    # 3. Selection des moments forts (LLM, fallback heuristique)
    emit("selecting", 0.50, "Selection des meilleurs moments")
    selected = llm.select_segments(transcript, config)
    if not selected:
        logger.error("Aucun segment selectionne, arret.")
        emit("done", 1.0, "Aucun segment")
        return {"video": src.title, "clips": []}
    emit("selecting", 0.60, f"{len(selected)} clips retenus")

    detector = FaceDetector(config.models_dir, min_confidence=config.face_confidence)
    words = transcript.all_words()
    logger.info("Sous-titres : backend %s.", report.subtitle_backend)

    n = len(selected)
    clips_meta: list[dict] = []
    for i, seg in enumerate(selected):
        clip_id = f"clip_{i:02d}"
        clip_dir = config.output_dir / clip_id
        clip_dir.mkdir(parents=True, exist_ok=True)
        base = 0.60 + 0.40 * i / n
        span = 0.40 / n
        logger.info("=== %s : %.1f-%.1fs | %s ===", clip_id, seg.start, seg.end, seg.title)

        try:
            # 5. Recadrage
            emit("reframing", base + span * 0.1, seg.title)
            plan = compute_reframe(
                src.path, seg.start, seg.end,
                models_dir=config.models_dir, detector=detector,
                scene_threshold=config.scene_threshold,
                samples_per_scene=config.samples_per_scene,
                per_scene=config.per_scene_reframe,
                mode=config.reframe_mode,
            )

            # 6. Sous-titres : ASS toujours ecrit (artefact portable) + overlay si besoin.
            emit("captioning", base + span * 0.4, seg.title)
            ass_path = clip_dir / "subs.ass"
            ass_path.write_text(
                generate_ass_for_clip(words, seg.start, seg.end, width=config.target_w, height=config.target_h),
                encoding="utf-8",
            )
            concat = None
            if report.subtitle_backend != "libass":
                concat = render_overlay_assets(
                    words, seg.start, seg.end, clip_dir / "_subs",
                    width=config.target_w, height=config.target_h,
                    font_path=config.caption_font, font_size=config.caption_font_size,
                )

            # 7. Rendu via l'EncoderProvider
            emit("rendering", base + span * 0.6, seg.title)
            out_path = clip_dir / "clip.mp4"
            encoder.encode_clip(
                src.path, seg.start, seg.end, plan, out_path,
                ass_path=ass_path, concat_path=concat,
                target_w=config.target_w, target_h=config.target_h,
                fps=config.fps, bitrate=config.video_bitrate,
            )
            shutil.rmtree(clip_dir / "_subs", ignore_errors=True)

            # Vignette
            thumb_path = clip_dir / "thumb.jpg"
            has_thumb = _make_thumbnail(out_path, thumb_path, at=min(2.0, (seg.end - seg.start) / 2))

            res = probe_resolution(out_path)
            meta = {
                "clip_id": clip_id,
                "order_index": i,
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
                "scenes": plan.n_scenes,
                "reframe_strategy": plan.strategy,
                "file": str(out_path.relative_to(config.output_dir)),
                "thumb": str(thumb_path.relative_to(config.output_dir)) if has_thumb else None,
            }
            (clip_dir / "meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            clips_meta.append(meta)
            emit("rendering", base + span, seg.title)
            if on_clip is not None:
                try:
                    on_clip(meta)
                except Exception:
                    logger.debug("on_clip a leve une exception", exc_info=True)
            logger.info("%s OK -> %sx%s", clip_id, meta["width"], meta["height"])
        except Exception as exc:
            logger.exception("Echec du clip %s : %s", clip_id, exc)

    index = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_url": src.url,
        "source_title": src.title,
        "source_duration": src.duration,
        "language": transcript.language,
        "selection_source": selected[0].source if selected else None,
        "clip_count": len(clips_meta),
        "clips": clips_meta,
    }
    (config.output_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    emit("done", 1.0, f"{len(clips_meta)} clips generes")
    logger.info("Termine : %d clip(s) dans %s", len(clips_meta), config.output_dir)
    return index
