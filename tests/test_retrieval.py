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


def test_count_reflects_upserts(tmp_path):
    store = LocalChromaVectorStore(persist_dir=str(tmp_path))
    assert store.count() == 0
    store.upsert(ids=["x"], texts=["some filing text"], metadatas=[{"ticker": "X"}])
    assert store.count() == 1
