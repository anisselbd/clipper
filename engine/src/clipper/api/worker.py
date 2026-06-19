"""Worker d'execution des jobs en tache de fond.

Un pool de threads (taille = concurrence, 1 par defaut au MVP) execute le
pipeline existant avec des callbacks de progression. Chaque clip rendu est
enregistre dans le JobStore avec ses cles de stockage, et publie en SSE.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from ..config import Config
from ..pipeline import run as run_pipeline
from ..providers import Providers
from .events import EventBus

logger = logging.getLogger("clipper.api.worker")


class JobWorker:
    def __init__(self, config: Config, providers: Providers, bus: EventBus, concurrency: int = 1) -> None:
        self.config = config
        self.providers = providers
        self.bus = bus
        self.executor = ThreadPoolExecutor(max_workers=max(1, concurrency), thread_name_prefix="clipper-job")

    def submit(self, job_id: str, url: str, params: dict) -> None:
        self.executor.submit(self._run, job_id, url, params)

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------ #

    def _job_config(self, job_id: str, params: dict) -> Config:
        return replace(
            self.config,
            clips=params.get("num_clips") or self.config.clips,
            lang=params.get("lang") or self.config.lang,
            whisper_model=params.get("whisper_model") or self.config.whisper_model,
            reframe_mode=params.get("reframe_mode") or self.config.reframe_mode,
            output_dir=self.config.data_dir / "jobs" / job_id / "output",
        )

    def _run(self, job_id: str, url: str, params: dict) -> None:
        store = self.providers.jobstore
        storage = self.providers.storage
        cfg = self._job_config(job_id, params)

        def on_progress(step: str, progress: float, message: str = "", detail: dict | None = None) -> None:
            store.update_job(job_id, status="running", step=step, progress=progress)
            self.bus.publish(job_id, {
                "type": "progress", "job_id": job_id,
                "step": step, "progress": progress, "message": message,
                "detail": detail,
            })

        def on_clip(meta: dict) -> None:
            file_abs = (cfg.output_dir / meta["file"]).resolve()
            file_key = storage.key_for_path(file_abs) if file_abs.exists() else None
            thumb_key = None
            if meta.get("thumb"):
                thumb_abs = (cfg.output_dir / meta["thumb"]).resolve()
                if thumb_abs.exists():
                    thumb_key = storage.key_for_path(thumb_abs)
            record = store.add_clip(job_id, {
                "clip_id": meta["clip_id"],
                "order_index": meta.get("order_index", 0),
                "title": meta.get("title"),
                "hook_score": meta.get("hook_score"),
                "duration": meta.get("duration"),
                "width": meta.get("width"),
                "height": meta.get("height"),
                "start": meta.get("start"),
                "end": meta.get("end"),
                "reason": meta.get("reason"),
                "selection_source": meta.get("selection_source"),
                "file_key": file_key,
                "thumb_key": thumb_key,
                "social": meta.get("social"),
            })
            self.bus.publish(job_id, {
                "type": "clip", "job_id": job_id,
                "clip_id": record["id"],
                "title": record.get("title"),
                "url": storage.get_url(file_key) if file_key else None,
                "thumb_url": storage.get_url(thumb_key) if thumb_key else None,
            })

        try:
            store.update_job(job_id, status="running", step="starting", progress=0.0)
            logger.info("Job %s demarre : %s", job_id, url)
            run_pipeline(
                url, cfg,
                on_progress=on_progress, on_clip=on_clip,
                report=self.providers.report,
                encoder=self.providers.encoder,
                llm=self.providers.llm,
            )
            store.update_job(job_id, status="done", step="done", progress=1.0)
            self.bus.publish(job_id, {"type": "done", "job_id": job_id})
            logger.info("Job %s termine.", job_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Job %s en echec : %s", job_id, exc)
            store.update_job(job_id, status="error", error=str(exc))
            self.bus.publish(job_id, {"type": "error", "job_id": job_id, "error": str(exc)})
        finally:
            self.bus.close(job_id)
