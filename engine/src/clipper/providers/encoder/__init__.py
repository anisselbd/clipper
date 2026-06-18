"""Provider d'encodage (local VideoToolbox/libx264, stub cloud NVENC)."""

from __future__ import annotations

from .base import EncoderProvider
from .local import LocalEncoder

__all__ = ["EncoderProvider", "LocalEncoder", "get_encoder_provider"]


def get_encoder_provider(report) -> EncoderProvider:
    return LocalEncoder.from_report(report)
