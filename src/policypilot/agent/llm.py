"""LLM client. Groq is the model provider everywhere, but the deployed path no longer talks
to Groq directly: it goes through the policypilot-groq-gateway Unity AI Gateway endpoint
(resources/serving_endpoint.yml), which holds the Groq key itself and adds PII/safety
guardrails Groq doesn't provide. Local dev still calls Groq directly with a raw
`GROQ_API_KEY` from `.env` — guardrail-free by design (see docs/UPGRADE_PLAN.md), since local
is a developer sandbox never exposed to untrusted users.
"""

from __future__ import annotations

from typing import Protocol

from policypilot.config import AI_GATEWAY_ENDPOINT, GROQ_MODEL, get_settings


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
    """Calls Groq via the Unity AI Gateway External Model endpoint instead of Groq directly.
    Auth is the Databricks App's own auto-injected service principal credentials
    (DATABRICKS_HOST/CLIENT_ID/CLIENT_SECRET), picked up automatically by WorkspaceClient's
    unified auth — the same credentials DatabricksVectorSearchStore already relies on, so
    there's no new credential to wire up."""

    def __init__(self, endpoint_name: str = AI_GATEWAY_ENDPOINT):
        from databricks.sdk import WorkspaceClient

        self._client = WorkspaceClient()
        self._endpoint_name = endpoint_name

    def complete(self, system: str, messages: list[dict]) -> str:
        from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

        chat_messages = [ChatMessage(role=ChatMessageRole.SYSTEM, content=system)] + [
            ChatMessage(role=ChatMessageRole(m["role"]), content=m["content"]) for m in messages
        ]
        response = self._client.serving_endpoints.query(
            name=self._endpoint_name, messages=chat_messages, max_tokens=1024
        )
        return response.choices[0].message.content or ""


def get_llm_client() -> LLMClient:
    settings = get_settings()
    if settings.is_local:
        if not settings.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        return GroqLLMClient(api_key=settings.groq_api_key)
    return DatabricksGatewayLLMClient()
