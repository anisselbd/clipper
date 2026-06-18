"""Routes HTTP : jobs, progression SSE, clips, fichiers."""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse

from .schemas import ClipResponse, CreateJobRequest, HealthResponse, JobResponse

logger = logging.getLogger("clipper.api.routes")
router = APIRouter()


def _state(request: Request):
    return request.app.state.config, request.app.state.providers, request.app.state.bus, request.app.state.worker


def _job_dict(store, job: dict) -> dict:
    job = dict(job)
    job["clip_count"] = len(store.list_clips(job["id"]))
    return job


def _clip_dict(storage, clip: dict) -> dict:
    return {
        "id": clip["id"],
        "clip_id": clip["clip_id"],
        "title": clip.get("title"),
        "hook_score": clip.get("hook_score"),
        "duration": clip.get("duration"),
        "width": clip.get("width"),
        "height": clip.get("height"),
        "start": clip.get("start"),
        "end": clip.get("end"),
        "reason": clip.get("reason"),
        "selection_source": clip.get("selection_source"),
        "url": storage.get_url(clip["file_key"]) if clip.get("file_key") else None,
        "thumb_url": storage.get_url(clip["thumb_key"]) if clip.get("thumb_key") else None,
    }


@router.get("/health", response_model=HealthResponse)
def health(request: Request):
    _, providers, _, _ = _state(request)
    return {"status": "ok", "preflight": providers.report.as_dict()}


@router.post("/jobs", response_model=JobResponse)
def create_job(req: CreateJobRequest, request: Request):
    config, providers, _, worker = _state(request)
    if not req.url.strip():
        raise HTTPException(status_code=422, detail="url manquante")
    job_id = uuid.uuid4().hex[:12]
    params = {
        "num_clips": req.num_clips,
        "lang": req.lang,
        "whisper_model": req.whisper_model,
        "reframe_mode": req.reframe_mode,
    }
    job = providers.jobstore.create_job(job_id, req.url.strip(), params)
    worker.submit(job_id, req.url.strip(), params)
    return _job_dict(providers.jobstore, job)


@router.get("/jobs", response_model=list[JobResponse])
def list_jobs(request: Request):
    _, providers, _, _ = _state(request)
    return [_job_dict(providers.jobstore, j) for j in providers.jobstore.list_jobs()]


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, request: Request):
    _, providers, _, _ = _state(request)
    job = providers.jobstore.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job introuvable")
    return _job_dict(providers.jobstore, job)


@router.get("/jobs/{job_id}/clips", response_model=list[ClipResponse])
def list_clips(job_id: str, request: Request):
    _, providers, _, _ = _state(request)
    if not providers.jobstore.get_job(job_id):
        raise HTTPException(status_code=404, detail="job introuvable")
    return [_clip_dict(providers.storage, c) for c in providers.jobstore.list_clips(job_id)]


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request):
    config, providers, bus, _ = _state(request)
    store = providers.jobstore
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job introuvable")

    async def gen():
        # Etat courant d'abord (utile si on s'abonne tard).
        yield {"event": "progress", "data": json.dumps({
            "type": "progress", "job_id": job_id,
            "step": job.get("step"), "progress": job.get("progress", 0),
            "status": job.get("status"),
        })}
        if job.get("status") in ("done", "error"):
            name = "job_error" if job["status"] == "error" else "done"
            yield {"event": name, "data": json.dumps({"type": job["status"], "job_id": job_id, "error": job.get("error")})}
            return

        q = bus.subscribe(job_id)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = q.get_nowait()
                except Exception:
                    await asyncio.sleep(0.2)
                    continue
                etype = ev.get("type")
                if etype == "_end":
                    break
                # 'error' renomme 'job_error' pour ne pas heurter l'event natif EventSource.
                name = "job_error" if etype == "error" else (etype or "message")
                yield {"event": name, "data": json.dumps(ev)}
                if etype in ("done", "error"):
                    break
        finally:
            bus.unsubscribe(job_id, q)

    return EventSourceResponse(gen())


@router.get("/clips/{clip_id}/file")
def clip_file(clip_id: str, request: Request):
    _, providers, _, _ = _state(request)
    clip = providers.jobstore.get_clip(clip_id)
    if not clip or not clip.get("file_key"):
        raise HTTPException(status_code=404, detail="clip introuvable")
    path = providers.storage.path_for(clip["file_key"])
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="fichier absent")
    return FileResponse(path, media_type="video/mp4", filename=f"{clip_id}.mp4")


@router.get("/files/{key:path}")
def serve_file(key: str, request: Request):
    _, providers, _, _ = _state(request)
    storage = providers.storage
    path = storage.path_for(key)
    if path is None:
        raise HTTPException(status_code=404, detail="non disponible")
    # Anti path-traversal : le chemin resolu doit rester sous la racine.
    root = storage.root.resolve()
    resolved = path.resolve()
    if root not in resolved.parents and resolved != root:
        raise HTTPException(status_code=403, detail="acces refuse")
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="fichier absent")
    media = "video/mp4" if resolved.suffix == ".mp4" else None
    return FileResponse(resolved, media_type=media)


@router.post("/jobs/{job_id}/reveal")
def reveal_job(job_id: str, request: Request):
    """Ouvre le dossier de sortie du job (desktop uniquement, no-op en cloud)."""
    config, providers, _, _ = _state(request)
    job = providers.jobstore.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job introuvable")
    folder = (config.data_dir / "jobs" / job_id / "output").resolve()
    if not folder.exists():
        raise HTTPException(status_code=404, detail="dossier absent")
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(folder)])
    elif sys.platform.startswith("linux"):
        subprocess.Popen(["xdg-open", str(folder)])
    elif sys.platform.startswith("win"):
        subprocess.Popen(["explorer", str(folder)])
    else:
        return JSONResponse({"opened": False, "path": str(folder)})
    return {"opened": True, "path": str(folder)}
