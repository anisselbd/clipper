"""Schemas Pydantic de l'API (contrat HTTP/JSON front <-> moteur)."""

from __future__ import annotations

from pydantic import BaseModel


class CreateJobRequest(BaseModel):
    url: str
    num_clips: int | None = None
    lang: str | None = None
    whisper_model: str | None = None


class JobResponse(BaseModel):
    id: str
    url: str
    status: str
    step: str | None = None
    progress: float = 0.0
    error: str | None = None
    created_at: str
    updated_at: str
    clip_count: int = 0


class ClipResponse(BaseModel):
    id: str
    clip_id: str
    title: str | None = None
    hook_score: int | None = None
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    start: float | None = None
    end: float | None = None
    reason: str | None = None
    selection_source: str | None = None
    url: str | None = None
    thumb_url: str | None = None


class HealthResponse(BaseModel):
    status: str
    preflight: dict
