"""Pluggable LLM client: direct Groq API for local dev, Databricks Model Serving
(via the AI Gateway) once a workspace exists. Both satisfy the same `complete` signature
so agent/graph.py never needs to know which one it's talking to.
"""

from __future__ import annotations

from typing import Protocol

from policypilot.config import GROQ_MODEL, get_settings


class LLMClient(Protocol):
    def complete(self, system: str, messages: list[dict]) -> str: ...


class GroqLLMClient:
    def __init__(self, api_key: str, model: str = GROQ_MODEL):
        from groq import Groq

        self._client = Groq(api_key=api_key)
        self._model = model

    def complete(self, system: str, messages: list[dict]) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "system", "content": system}, *messages],
        )
        return response.choices[0].message.content or ""


class DatabricksModelServingClient:
    """Fill in once a Model Serving endpoint is deployed behind the Unity AI Gateway."""

    def __init__(self, *, endpoint_name: str):
        raise NotImplementedError(
            "DatabricksModelServingClient requires a deployed Model Serving endpoint. "
            "See README 'Next steps' for the provisioning checklist."
        )

    def complete(self, system: str, messages: list[dict]) -> str:
        raise NotImplementedError


def get_llm_client() -> LLMClient:
    settings = get_settings()
    if settings.is_local:
        if not settings.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        return GroqLLMClient(api_key=settings.groq_api_key)
    return DatabricksModelServingClient(endpoint_name="policypilot-agent")
