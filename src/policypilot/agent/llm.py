"""LLM client. Groq is the provider in both local and Databricks deployments right now —
`GROQ_API_KEY` comes from `.env` locally and from the Key Vault-backed secret scope
(`policypilot-kv-scope`/`groq-api-key`) once deployed as a Databricks App/Job, injected
as the same env var either way. Swapping to a Databricks-native model (Foundation Model
APIs or an Azure OpenAI External Model behind Unity AI Gateway — real "Mosaic AI"
adoption) is a deliberate future step, not required for the agent to work end-to-end.
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


def get_llm_client() -> LLMClient:
    settings = get_settings()
    if not settings.groq_api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Locally: copy .env.example to .env and add your key. "
            "Deployed: bind the policypilot-kv-scope/groq-api-key secret as this env var."
        )
    return GroqLLMClient(api_key=settings.groq_api_key)
