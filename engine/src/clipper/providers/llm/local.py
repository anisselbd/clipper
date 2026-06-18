"""Impl locale du LLMProvider : llama-server + fallback heuristique.

Delegue a clipper.segment (logique existante, non reecrite) : sortie structuree
json_schema, thinking-off, temperature 0, reessais, et bascule heuristique si le
serveur est injoignable (promesse local-first).
"""

from __future__ import annotations

from ...config import Config
from ...transcribe import Transcript
from .base import LLMProvider


class LocalLLMProvider(LLMProvider):
    name = "local_llm"

    def select_segments(self, transcript: Transcript, config: Config) -> list:
        # Import tardif pour eviter un cycle (segment importe les providers).
        from ...segment import select_segments

        return select_segments(transcript, config)
