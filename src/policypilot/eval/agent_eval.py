"""Eval harness: runs the golden dataset through the agent via Databricks Agent Evaluation
(mlflow.genai.evaluate), using Databricks-hosted judges for groundedness, safety, and
relevance instead of the retired custom MLflow-judge harness (run_eval.py).

Retrieval is wrapped in a RETRIEVER-typed trace span (see `_traced_search` below) purely for
this eval run, so the RetrievalGroundedness judge can see what was actually retrieved — the
core agent code (agent/graph.py, agent/tools.py) stays free of any mlflow dependency, since
it also runs in the deployed app where mlflow isn't installed.

Requires `GROQ_API_KEY` (to run the agent) and Databricks workspace auth (for the hosted
judges) — see docs/DEPLOYMENT_GUIDE.md. Runs against a local vector store (PP_ENV-driven,
same as the app), so it never depends on a live Databricks Vector Search endpoint.
"""

from __future__ import annotations

import json

import mlflow
from mlflow.entities import Document, SpanType
from mlflow.genai.scorers import RelevanceToQuery, RetrievalGroundedness, Safety, scorer

from policypilot.agent.graph import CITATION_RE, ask
from policypilot.agent.llm import LLMClient, get_llm_client
from policypilot.config import REPO_ROOT, get_settings
from policypilot.ingestion.pipeline import get_vector_store
from policypilot.retrieval.base import SearchResult, VectorStore

GOLDEN_PATH = REPO_ROOT / "src" / "policypilot" / "eval" / "golden_dataset.jsonl"


class _TracedVectorStore:
    """Wraps a VectorStore so `search` is recorded as a RETRIEVER trace span — the shape
    Databricks' RetrievalGroundedness judge expects — without adding an mlflow dependency
    to the core retrieval/agent modules that also run in the (mlflow-free) deployed app."""

    def __init__(self, inner: VectorStore):
        self._inner = inner

    def upsert(self, ids, texts, metadatas):
        self._inner.upsert(ids, texts, metadatas)

    @mlflow.trace(span_type=SpanType.RETRIEVER)
    def search(self, query: str, k: int = 5) -> list[SearchResult]:
        results = self._inner.search(query, k=k)
        span = mlflow.get_current_active_span()
        if span is not None:
            span.set_outputs(
                [
                    Document(page_content=r.text, metadata=r.metadata or {}, id=str(i))
                    for i, r in enumerate(results)
                ]
            )
        return results


def load_golden_dataset() -> list[dict]:
    return [json.loads(line) for line in GOLDEN_PATH.read_text().splitlines() if line.strip()]


@scorer
def citation_present(outputs: str) -> bool:
    """Cheap, non-LLM gate: does the answer carry the required [N] citation format?"""
    return bool(CITATION_RE.search(outputs))


def _build_predict_fn(llm: LLMClient, store: VectorStore):
    traced_store = _TracedVectorStore(store)

    @mlflow.trace(span_type=SpanType.AGENT)
    def predict(question: str) -> str:
        result = ask(llm, traced_store, question)
        return result["final_answer"]

    return predict


def run_agent_eval() -> dict:
    settings = get_settings()
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not set — required to run the agent.")

    llm = get_llm_client()
    store = get_vector_store()
    dataset = load_golden_dataset()

    data = [{"inputs": {"question": item["question"]}} for item in dataset]
    predict_fn = _build_predict_fn(llm, store)

    results = mlflow.genai.evaluate(
        data=data,
        predict_fn=predict_fn,
        scorers=[Safety(), RelevanceToQuery(), RetrievalGroundedness(), citation_present],
    )

    print(f"\nQuestions evaluated: {len(data)}")
    print(results.metrics)
    return results.metrics


if __name__ == "__main__":
    run_agent_eval()
