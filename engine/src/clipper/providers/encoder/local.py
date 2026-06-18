"""Encodeur local : enveloppe render.py, chemins choisis par le preflight.

Encodeur video : h264_videotoolbox ou libx264 (report.video_encoder).
Sous-titres : libass natif ou overlay PNG (report.subtitle_backend).
"""

from __future__ import annotations

import logging
from pathlib import Path

from ...reframe import ReframePlan
from ...render import render_clip, render_clip_overlay
from .base import EncoderProvider

logger = logging.getLogger("clipper.encoder")


class LocalEncoder(EncoderProvider):
    name = "local"

    def __init__(self, video_encoder: str, subtitle_backend: str) -> None:
        self.video_encoder = video_encoder
        self.subtitle_backend = subtitle_backend

    @classmethod
    def from_report(cls, report) -> "LocalEncoder":
        return cls(video_encoder=report.video_encoder, subtitle_backend=report.subtitle_backend)

    def encode_clip(
        self,
        source: Path,
        start: float,
        end: float,
        plan: ReframePlan,
        out_path: Path,
        *,
        ass_path: Path | None = None,
        concat_path: Path | None = None,
        target_w: int = 1080,
        target_h: int = 1920,
        fps: int = 30,
        bitrate: str = "8M",
    ) -> Path:
        if self.subtitle_backend == "libass" and ass_path is not None:
            return render_clip(
                source, start, end, plan, ass_path, out_path,
                target_w=target_w, target_h=target_h, fps=fps,
                encoder=self.video_encoder, bitrate=bitrate,
            )
        return render_clip_overlay(
            source, start, end, plan, concat_path, out_path,
            target_w=target_w, target_h=target_h, fps=fps,
            encoder=self.video_encoder, bitrate=bitrate,
        )
