"""STUB cloud (phase 2) : selection via un LLM heberge.

En SaaS, le moteur tourne sur un worker GPU et la selection peut passer par un
endpoint LLM heberge (vLLM derriere une URL privee, ou une API type OpenAI /
Anthropic). L'interface reste identique : select_segments(transcript) renvoie
des timestamps.
"""

from __future__ import annotations

from ...config import Config
from ...transcribe import Transcript
from .base import LLMProvider


class HostedLLMProvider(LLMProvider):
    name = "hosted_llm"

    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    def select_segments(self, transcript: Transcript, config: Config) -> list:
        # TODO (phase 2) : meme logique que LocalLLMProvider mais en pointant
        # LLM_BASE_URL vers l'endpoint heberge. La sortie structuree et le
        # fallback restent identiques. Penser a l'auth (cle privee) et au
        # rate-limit.
        raise NotImplementedError("HostedLLMProvider : stub phase 2.")
