"""STUB cloud (phase 2) : encodage GPU NVENC sur worker."""

from __future__ import annotations

from pathlib import Path

from ...reframe import ReframePlan
from .base import EncoderProvider


class NvencEncoder(EncoderProvider):
    name = "nvenc"

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
        delogo: str = "",
    ) -> Path:
        # TODO (phase 2) : meme filtergraph que LocalEncoder mais -c:v h264_nvenc
        # (worker GPU). Le build ffmpeg du worker doit embarquer libass pour le
        # chemin sous-titres natif (sinon overlay PNG comme en local).
        raise NotImplementedError("NvencEncoder : stub phase 2 (worker GPU).")
