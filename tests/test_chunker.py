from policypilot.ingestion.chunker import chunk_filing

FILING = {
    "company": "Test Co",
    "filing_date": "2026-01-01",
    "accession_number": "0000000000-26-000001",
}


def test_chunk_filing_splits_long_text():
    text = " ".join(f"word{i}" for i in range(3000))
    chunks = chunk_filing("TST", FILING, text)
    assert len(chunks) > 1
    assert all(c.ticker == "TST" for c in chunks)
    assert all(c.company == "Test Co" for c in chunks)
    assert chunks[0].id == "TST-0000000000-26-000001-0"


def test_chunk_filing_empty_text_returns_no_chunks():
    assert chunk_filing("TST", FILING, "") == []


def test_chunk_filing_short_text_returns_single_chunk():
    chunks = chunk_filing("TST", FILING, "short filing text")
    assert len(chunks) == 1
    assert chunks[0].text == "short filing text"
