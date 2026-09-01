"""fetch -> chunk -> embed -> store, as one function. Callable locally today (see
__main__ below) and, unchanged, as the Lakeflow job task once resources/jobs.yml is
deployed against a real workspace.
"""

from __future__ import annotations

import logging

from policypilot.config import (
    DATA_DIR,
    DEFAULT_TICKERS,
    RAW_DIR,
    VECTOR_SEARCH_ENDPOINT,
    VECTOR_SEARCH_INDEX,
    get_settings,
)
from policypilot.ingestion.chunker import chunk_filing
from policypilot.ingestion.edgar_client import EdgarClient
from policypilot.ingestion.manifest import record_filing
from policypilot.retrieval.base import VectorStore
from policypilot.retrieval.local_chroma import LocalChromaVectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def get_vector_store() -> VectorStore:
    settings = get_settings()
    if settings.is_local:
        return LocalChromaVectorStore()
    from policypilot.retrieval.databricks_vector_search import DatabricksVectorSearchStore

    return DatabricksVectorSearchStore(
        endpoint_name=VECTOR_SEARCH_ENDPOINT, index_name=VECTOR_SEARCH_INDEX
    )


def run_ingestion(tickers: list[str] | None = None) -> int:
    """Fetch each ticker's latest 10-K, chunk it, embed it, and upsert into the
    configured vector store. Returns the total number of chunks indexed."""
    settings = get_settings()
    tickers = tickers or DEFAULT_TICKERS
    client = EdgarClient(user_agent=settings.sec_user_agent)
    store = get_vector_store()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    total_chunks = 0
    for ticker in tickers:
        logger.info("Fetching CIK for %s", ticker)
        cik = client.get_cik_for_ticker(ticker)

        logger.info("Looking up most recent 10-K for %s (CIK %s)", ticker, cik)
        filing = client.get_recent_10k(cik)

        logger.info(
            "Downloading %s filed %s (accession %s)",
            filing["company"],
            filing["filing_date"],
            filing["accession_number"],
        )
        text = client.download_filing_text(filing)
        (RAW_DIR / f"{ticker}_{filing['accession_number']}.txt").write_text(text)
        record_filing(ticker, filing)

        chunks = chunk_filing(ticker, filing, text)
        logger.info("Chunked %s into %d chunks", ticker, len(chunks))

        store.upsert(
            ids=[c.id for c in chunks],
            texts=[c.text for c in chunks],
            metadatas=[
                {
                    "ticker": c.ticker,
                    "company": c.company,
                    "filing_date": c.filing_date,
                    "accession_number": c.accession_number,
                    "chunk_index": c.chunk_index,
                }
                for c in chunks
            ],
        )
        total_chunks += len(chunks)

    logger.info(
        "Ingestion complete: %d chunks indexed across %d tickers", total_chunks, len(tickers)
    )
    return total_chunks


if __name__ == "__main__":
    run_ingestion()
