from policypilot.agent.graph import REFUSAL_MESSAGE, ask
from policypilot.retrieval.base import SearchResult


class FakeStore:
    def __init__(self, results: list[SearchResult]):
        self._results = results

    def upsert(self, ids, texts, metadatas):
        pass

    def search(self, query: str, k: int = 5) -> list[SearchResult]:
        return self._results[:k]


class FakeLLM:
    def __init__(self, answer: str, search_query: str = "supply chain risk"):
        self._answer = answer
        self._search_query = search_query

    def complete(self, system: str, messages: list[dict]) -> str:
        if system.startswith("You turn a user's question"):
            return self._search_query
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
    llm = FakeLLM(answer="This should never be returned [1].")

    result = ask(llm, store, "What is the capital of France?")

    assert result["grounded"] is False
    assert result["final_answer"] == REFUSAL_MESSAGE
