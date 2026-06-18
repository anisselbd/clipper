"""Fournisseur Anthropic (STUB - phase 2, non implemente).

Squelette volontairement non fonctionnel pour cadrer l'extension future.
"""

from __future__ import annotations

from .base import LLMProvider


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, model: str, api_key: str | None = None, timeout: float = 180.0) -> None:
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str:
        # TODO (phase 2) : appeler l'API Messages d'Anthropic.
        #   from anthropic import Anthropic
        #   client = Anthropic(api_key=self.api_key)
        #   msg = client.messages.create(
        #       model=self.model, system=system, max_tokens=max_tokens,
        #       temperature=temperature,
        #       messages=[{"role": "user", "content": user}],
        #   )
        #   return msg.content[0].text
        # Penser a ajouter `anthropic` aux dependances et a documenter ANTHROPIC_API_KEY.
        raise NotImplementedError(
            "AnthropicProvider est un stub (phase 2). "
            "Utilise LLM_PROVIDER=local_llm pour le MVP."
        )
