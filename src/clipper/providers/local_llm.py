"""Fournisseur LLM local via endpoint compatible OpenAI.

Cible par defaut : llama-server (llama.cpp) servant Qwen3 sur
http://localhost:8080/v1. Tout endpoint exposant /chat/completions au format
OpenAI fonctionne (vLLM, LM Studio, Ollama en mode OpenAI, etc.).
"""

from __future__ import annotations

import httpx

from .base import LLMProvider, ProviderUnavailable


class LocalLLMProvider(LLMProvider):
    name = "local_llm"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 180.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
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
        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
        except (httpx.HTTPError, OSError) as exc:
            raise ProviderUnavailable(f"endpoint LLM injoignable ({url}): {exc}") from exc

        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, ValueError) as exc:
            raise ProviderUnavailable(f"reponse LLM inattendue: {exc}") from exc
