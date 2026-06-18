"""Provider LLM : selection des segments (local par defaut, stub cloud)."""

from __future__ import annotations

from ...config import Config
from .base import LLMProvider
from .client import ChatClient, ProviderUnavailable, build_chat_client
from .local import LocalLLMProvider

__all__ = [
    "LLMProvider",
    "LocalLLMProvider",
    "ChatClient",
    "ProviderUnavailable",
    "build_chat_client",
    "get_llm_provider",
]


def get_llm_provider(config: Config) -> LLMProvider:
    provider = (config.llm_provider or "local_llm").lower()
    if provider in ("local_llm", "local", "openai", "llama"):
        return LocalLLMProvider()
    if provider in ("hosted", "cloud", "hosted_llm"):
        from .cloud_stub import HostedLLMProvider

        return HostedLLMProvider()
    # Defaut sur du local plutot que d'echouer.
    return LocalLLMProvider()
