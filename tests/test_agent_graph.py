import json

from policypilot.agent.graph import REFUSAL_MESSAGE, ask
from policypilot.retrieval.base import SearchResult


class FakeStore:
    def __init__(self, results: list[SearchResult]):
        self._results = results
        self.last_ticker: str | None = "unset"

    def upsert(self, ids, texts, metadatas):
        pass

    def search(self, query: str, k: int = 5, ticker: str | None = None) -> list[SearchResult]:
        self.last_ticker = ticker
        return self._results[:k]


class FakeLLM:
    def __init__(
        self, answer: str, search_query: str = "supply chain risk", ticker: str | None = "AAPL"
    ):
        self._answer = answer
        self._search_query = search_query
        self._ticker = ticker

    def complete(self, system: str, messages: list[dict]) -> str:
        if system.startswith("You turn a user's question"):
            return json.dumps({"search_query": self._search_query, "ticker": self._ticker})
        if system.startswith("You are PolicyPilot"):
            return self._answer
        raise AssertionError(f"Unexpected system prompt: {system[:50]!r}")


SAMPLE_RESULT = SearchResult(
    text="Apple's 10-K discusses reliance on a limited number of suppliers.",
    score=0.9,
    metadata={"company": "Apple Inc.", "filing_date": "2025-11-01", "accession_number": "acc-1"},
)


def test_agent_returns_grounded_answer_with_citation():
    store = FakeStore([SAMPLE_RESULT])
    llm = FakeLLM(answer="Apple discloses supplier concentration risk [1].")

    result = ask(llm, store, "What supply chain risks does Apple disclose?")

    assert result["grounded"] is True
    assert result["final_answer"] == "Apple discloses supplier concentration risk [1]."


def test_agent_refuses_when_answer_has_no_citation():
    store = FakeStore([SAMPLE_RESULT])
    llm = FakeLLM(answer="Apple discloses supplier concentration risk.")  # no [1]

    result = ask(llm, store, "What supply chain risks does Apple disclose?")

    assert result["grounded"] is False
    assert result["final_answer"] == REFUSAL_MESSAGE


def test_agent_refuses_when_no_results_retrieved():
    store = FakeStore([])
    llm = FakeLLM(answer="This should never be returned [1].", ticker=None)

    result = ask(llm, store, "What is the capital of France?")

    assert result["grounded"] is False
    assert result["final_answer"] == REFUSAL_MESSAGE
    assert store.last_ticker is None


def test_agent_scopes_retrieval_to_resolved_ticker():
    """Regression test: the plan step resolving a ticker must actually reach the vector
    search call — otherwise retrieval can return another company's chunks entirely, which
    is exactly what happened in production once the corpus grew past a handful of tickers."""
    store = FakeStore([SAMPLE_RESULT])
    llm = FakeLLM(answer="Apple discloses supplier concentration risk [1].", ticker="AAPL")

    ask(llm, store, "What supply chain risks does Apple disclose?")

    assert store.last_ticker == "AAPL"
