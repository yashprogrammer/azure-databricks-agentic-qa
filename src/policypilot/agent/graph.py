"""LangGraph agent: plan -> retrieve -> answer -> verify.

Genuinely agentic rather than a bare RAG chain: the plan step decides what to search for
and whether a structured metadata lookup applies, and the verify step is a hard gate —
an answer without a citation back to a retrieved chunk is replaced with a refusal instead
of being returned to the user.
"""

from __future__ import annotations

import re
from typing import TypedDict

from langgraph.graph import END, StateGraph

from policypilot.agent.llm import LLMClient
from policypilot.agent.tools import filing_metadata, format_context, retrieve
from policypilot.config import DEFAULT_TICKERS
from policypilot.retrieval.base import SearchResult, VectorStore

CITATION_RE = re.compile(r"\[\d+\]")

PLAN_SYSTEM_PROMPT = (
    "You turn a user's question about SEC 10-K filings into a short search query "
    "for a semantic search index over filing text. If the question names a specific "
    "company ticker, include it in the query. Reply with ONLY the search query text, "
    "nothing else."
)

ANSWER_SYSTEM_PROMPT = (
    "You are PolicyPilot, a compliance research assistant that answers questions about "
    "SEC 10-K filings using ONLY the numbered context provided below. This is a strict "
    "citation requirement: every sentence containing a factual claim MUST end with a "
    "bracketed citation number like [1] or [2] matching the context item it came from — "
    "no other citation style (no footnotes, no parentheses, no 'Source:' lines). "
    "Example: 'The filing discloses reliance on a limited number of suppliers [1].' "
    "If the context does not contain enough information to answer, say so plainly instead "
    "of guessing — never answer from general knowledge.\n\nContext:\n{context}"
)

REFUSAL_MESSAGE = (
    "I don't have enough grounded information in the ingested filings to answer that "
    "confidently. Try rephrasing, or ask about one of the ingested companies."
)


class AgentState(TypedDict, total=False):
    question: str
    search_query: str
    ticker_hint: str | None
    results: list[SearchResult]
    metadata: dict | None
    draft_answer: str
    final_answer: str
    grounded: bool


def build_graph(llm: LLMClient, store: VectorStore):
    def plan_node(state: AgentState) -> AgentState:
        query = llm.complete(
            system=PLAN_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": state["question"]}],
        ).strip()
        words = {w.strip(".,?!").upper() for w in state["question"].split()}
        ticker_hint = next((t for t in DEFAULT_TICKERS if t in words), None)
        return {"search_query": query or state["question"], "ticker_hint": ticker_hint}

    def retrieve_node(state: AgentState) -> AgentState:
        results = retrieve(store, state["search_query"], k=5)
        metadata = filing_metadata(state["ticker_hint"]) if state.get("ticker_hint") else None
        return {"results": results, "metadata": metadata}

    def answer_node(state: AgentState) -> AgentState:
        context = format_context(state["results"])
        if not context:
            return {"draft_answer": REFUSAL_MESSAGE}
        system = ANSWER_SYSTEM_PROMPT.format(context=context)
        draft = llm.complete(
            system=system, messages=[{"role": "user", "content": state["question"]}]
        )
        return {"draft_answer": draft}

    def verify_node(state: AgentState) -> AgentState:
        draft = state["draft_answer"]
        grounded = bool(state.get("results")) and bool(CITATION_RE.search(draft))
        final = draft if grounded else REFUSAL_MESSAGE
        return {"final_answer": final, "grounded": grounded}

    graph = StateGraph(AgentState)
    graph.add_node("plan", plan_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("answer", answer_node)
    graph.add_node("verify", verify_node)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "retrieve")
    graph.add_edge("retrieve", "answer")
    graph.add_edge("answer", "verify")
    graph.add_edge("verify", END)

    return graph.compile()


def ask(llm: LLMClient, store: VectorStore, question: str) -> AgentState:
    app = build_graph(llm, store)
    return app.invoke({"question": question})
