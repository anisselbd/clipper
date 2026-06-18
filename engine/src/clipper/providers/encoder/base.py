"""Interface EncoderProvider : encodage d'un clip (crop + sous-titres).

Point de bascule SaaS n.3. En local : VideoToolbox (ou libx264) + incrustation
libass ou overlay PNG, choisis d'apres le preflight. En cloud : NVENC.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ...reframe import ReframePlan


class EncoderProvider(ABC):
    @abstractmethod
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
        ...
