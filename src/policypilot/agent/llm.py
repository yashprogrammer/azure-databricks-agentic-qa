"""LLM client. Groq is the model provider everywhere, but the deployed path no longer talks
to Groq directly: it goes through a Unity Gateway model service (resources/ai_gateway.yml),
whose model provider service holds the Groq key, and which adds guardrails/rate limits Groq
doesn't provide. Local dev still calls Groq directly with a raw
`GROQ_API_KEY` from `.env` — guardrail-free by design (see docs/UPGRADE_PLAN.md), since local
is a developer sandbox never exposed to untrusted users.
"""

from __future__ import annotations

from typing import Protocol

from policypilot.config import AI_GATEWAY_MODEL_SERVICE, GROQ_MODEL, get_settings


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


class DatabricksGatewayLLMClient:
    """Calls Groq via the Unity Gateway model service instead of Groq directly, through the
    OpenAI-compatible unified API (POST /ai-gateway/mlflow/v1/chat/completions, with the
    model service's three-part UC name as `model`). Auth is the Databricks App's own
    auto-injected service principal credentials (DATABRICKS_HOST/CLIENT_ID/CLIENT_SECRET),
    picked up by WorkspaceClient's unified auth — the same credentials
    DatabricksVectorSearchStore already relies on, so there's no new credential to wire up."""

    def __init__(self, model_service: str = AI_GATEWAY_MODEL_SERVICE):
        from databricks.sdk import WorkspaceClient

        self._client = WorkspaceClient()
        self._model_service = model_service

    def complete(self, system: str, messages: list[dict]) -> str:
        response = self._client.api_client.do(
            "POST",
            "/ai-gateway/mlflow/v1/chat/completions",
            body={
                "model": self._model_service,
                "max_tokens": 1024,
                "messages": [{"role": "system", "content": system}, *messages],
            },
        )
        return response["choices"][0]["message"]["content"] or ""


def get_llm_client() -> LLMClient:
    settings = get_settings()
    if settings.is_local:
        if not settings.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        return GroqLLMClient(api_key=settings.groq_api_key)
    return DatabricksGatewayLLMClient()
