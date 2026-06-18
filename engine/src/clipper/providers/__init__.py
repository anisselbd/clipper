"""Selection du fournisseur LLM (pluggable via config)."""

from __future__ import annotations

from ..config import Config
from .anthropic import AnthropicProvider
from .base import LLMProvider, ProviderUnavailable
from .local_llm import LocalLLMProvider

__all__ = ["LLMProvider", "ProviderUnavailable", "get_provider"]


def get_provider(config: Config) -> LLMProvider:
    provider = config.llm_provider.lower()
    if provider in ("local_llm", "local", "openai", "llama"):
        extra_body: dict = {}
        if config.llm_disable_thinking:
            # Convention Qwen3 via llama.cpp --jinja ; ignore par les autres.
            extra_body["chat_template_kwargs"] = {"enable_thinking": False}
        return LocalLLMProvider(
            base_url=config.llm_base_url,
            model=config.llm_model,
            api_key=config.llm_api_key,
            timeout=config.llm_timeout,
            extra_body=extra_body,
        )
    if provider == "anthropic":
        return AnthropicProvider(
            model=config.llm_model,
            api_key=config.llm_api_key,
            timeout=config.llm_timeout,
        )
    raise ValueError(f"Fournisseur LLM inconnu : {config.llm_provider!r}")
