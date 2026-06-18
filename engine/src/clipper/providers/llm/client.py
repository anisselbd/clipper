"""Client bas niveau OpenAI-compatible (llama-server, vLLM, LM Studio, ...).

Sortie structuree (lecon RETEX) : supporte response_format json_schema cote
serveur pour garantir un JSON conforme, et chat_template_kwargs pour desactiver
le thinking de Qwen3.
"""

from __future__ import annotations

import httpx


class ProviderUnavailable(RuntimeError):
    """Le service LLM est injoignable (reseau, serveur arrete, timeout).

    Intercepte en amont pour basculer sur le fallback heuristique.
    """


class ChatClient:
    """Appel /chat/completions, renvoie le contenu texte de la reponse."""

    name = "local_llm"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 180.0,
        extra_body: dict | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.extra_body = extra_body or {}

    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        response_format: dict | None = None,
    ) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            **self.extra_body,
        }
        if response_format is not None:
            payload["response_format"] = response_format

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


def build_chat_client(config) -> ChatClient:
    extra_body: dict = {}
    if config.llm_disable_thinking:
        # Convention Qwen3 via llama.cpp --jinja ; ignore par les autres modeles.
        extra_body["chat_template_kwargs"] = {"enable_thinking": False}
    return ChatClient(
        base_url=config.llm_base_url,
        model=config.llm_model,
        api_key=config.llm_api_key,
        timeout=config.llm_timeout,
        extra_body=extra_body,
    )
