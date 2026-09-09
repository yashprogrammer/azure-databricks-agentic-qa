"""Tutorial demo: streams the LangGraph agent node-by-node instead of just printing the
final answer — so learners can see plan -> retrieve -> answer -> verify fire in sequence,
with the actual state (search query, resolved ticker, retrieved chunks, citation gate
pass/fail) at each step.

Usage:
    uv run python scripts/demo_agent_trace.py "What risk factors does Apple disclose?"
    uv run python scripts/demo_agent_trace.py                      # uses a default question
    uv run python scripts/demo_agent_trace.py "What is the capital of France?"  # refusal demo
"""

from __future__ import annotations

import sys

from policypilot.agent.graph import build_graph
from policypilot.agent.llm import get_llm_client
from policypilot.ingestion.pipeline import get_vector_store

DEFAULT_QUESTION = "What risk factors does Apple disclose about its supply chain?"

# Keep printed values short enough to read on screen during a live demo.
_MAX_LEN = 280


def _short(value) -> str:
    text = str(value)
    return text if len(text) <= _MAX_LEN else text[:_MAX_LEN] + "…"


def main() -> None:
    question = " ".join(sys.argv[1:]) or DEFAULT_QUESTION

    print("Loading agent (LLM client + vector store)...")
    llm = get_llm_client()
    store = get_vector_store()
    app = build_graph(llm, store)

    print(f"\nQuestion: {question}\n")
    print("=" * 70)

    for step in app.stream({"question": question}):
        for node, state in step.items():
            print(f"\n>>> NODE: {node.upper()}")
            for key, value in state.items():
                if key == "results" and value:
                    print(f"  results: {len(value)} chunk(s) retrieved")
                    for i, r in enumerate(value[:3], start=1):
                        print(f"    [{i}] {r.metadata.get('company')} — {_short(r.text)}")
                    if len(value) > 3:
                        print(f"    ... and {len(value) - 3} more")
                else:
                    print(f"  {key}: {_short(value)}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
