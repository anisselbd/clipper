"""Interface LLMProvider : selection des segments forts.

Point de bascule SaaS n.1. Le LLM SELECTIONNE des passages existants (renvoie
des timestamps), il n'invente jamais de contenu.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ...config import Config
from ...transcribe import Transcript


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def select_segments(self, transcript: Transcript, config: Config, audio_peaks=None, on_progress=None) -> list:
        """Renvoie une liste de SelectedSegment (cf. clipper.segment).

        audio_peaks : reactions sonores fortes optionnelles (cf. highlights).
        on_progress : callback (fraction, detail) de progression par fenetre.
        """
        raise NotImplementedError
