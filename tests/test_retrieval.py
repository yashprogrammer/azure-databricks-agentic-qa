from policypilot.retrieval.local_chroma import LocalChromaVectorStore


def test_upsert_and_search_returns_relevant_result(tmp_path):
    store = LocalChromaVectorStore(persist_dir=str(tmp_path))
    store.upsert(
        ids=["a", "b"],
        texts=[
            "Apple discusses supply chain risk factors in its 10-K filing.",
            "The recipe calls for two cups of flour and one egg.",
        ],
        metadatas=[{"ticker": "AAPL"}, {"ticker": "NONE"}],
    )

    results = store.search("What supply chain risks does Apple disclose?", k=1)

    assert len(results) == 1
    assert results[0].metadata["ticker"] == "AAPL"


def test_search_with_ticker_filter_excludes_other_companies(tmp_path):
    """Regression test: with many companies' filings using near-identical boilerplate risk
    language, pure semantic search can surface the wrong company's chunks. Once a ticker is
    known, search must be scoped to it rather than trusting similarity alone."""
    store = LocalChromaVectorStore(persist_dir=str(tmp_path))
    store.upsert(
        ids=["nvda-1", "csco-1"],
        texts=[
            "NVIDIA discusses semiconductor supply and demand risk in its 10-K.",
            "Cisco discusses semiconductor supply and demand risk in its 10-K.",
        ],
        metadatas=[{"ticker": "NVDA"}, {"ticker": "CSCO"}],
    )

    results = store.search("semiconductor supply and demand risk", k=5, ticker="NVDA")

    assert len(results) == 1
    assert results[0].metadata["ticker"] == "NVDA"


def test_count_reflects_upserts(tmp_path):
    store = LocalChromaVectorStore(persist_dir=str(tmp_path))
    assert store.count() == 0
    store.upsert(ids=["x"], texts=["some filing text"], metadatas=[{"ticker": "X"}])
    assert store.count() == 1
