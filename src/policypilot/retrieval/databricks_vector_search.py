"""Production VectorStore backend: Databricks Vector Search over a Delta-synced UC table.

Uses self-managed embeddings (the `embedding` column in policypilot_dev.filings.chunks,
computed with the same sentence-transformers model as local dev) so switching from
LocalChromaVectorStore never changes embedding dimensionality or retrieval semantics —
only where the vectors live. Provisioning is a one-time click-through in the workspace UI
(create the endpoint + Delta-Sync index over policypilot_dev.filings.chunks with
`embedding` as the embedding vector column) — see README "Next steps".

New chunks are written directly to the Delta table (see notebooks/seed_chunks_table.py);
the Delta-Sync index picks them up automatically via Change Data Feed, so `upsert` here
is intentionally not the ingestion path — it exists only to satisfy the VectorStore
protocol for any code that calls it generically.
"""

from __future__ import annotations

import os

from policypilot.config import EMBEDDING_MODEL
from policypilot.retrieval.base import SearchResult

RESULT_COLUMNS = ["chunk_id", "text", "ticker", "company", "filing_date", "accession_number"]


class DatabricksVectorSearchStore:
    def __init__(self, *, endpoint_name: str, index_name: str):
        from databricks.vector_search.client import VectorSearchClient
        from sentence_transformers import SentenceTransformer

        # VectorSearchClient's auto-detection relies on MLflow's notebook-context
        # resolver, which doesn't apply inside a Databricks App process. Databricks
        # Apps inject DATABRICKS_HOST/CLIENT_ID/CLIENT_SECRET for the app's own
        # service principal — pass those explicitly instead. DATABRICKS_HOST is
        # injected as a bare hostname (no scheme), which the client requires.
        host = os.environ.get("DATABRICKS_HOST")
        if host and not host.startswith("http"):
            host = f"https://{host}"
        self._client = VectorSearchClient(
            workspace_url=host,
            service_principal_client_id=os.environ.get("DATABRICKS_CLIENT_ID"),
            service_principal_client_secret=os.environ.get("DATABRICKS_CLIENT_SECRET"),
        )
        self._index = self._client.get_index(endpoint_name=endpoint_name, index_name=index_name)
        self._embedder = SentenceTransformer(EMBEDDING_MODEL)

    def upsert(self, ids: list[str], texts: list[str], metadatas: list[dict]) -> None:
        raise NotImplementedError(
            "Write new chunks to policypilot_dev.filings.chunks directly (see "
            "notebooks/seed_chunks_table.py) — the Delta-Sync index picks up changes "
            "automatically via Change Data Feed."
        )

    def search(self, query: str, k: int = 5) -> list[SearchResult]:
        query_vector = self._embedder.encode([query], show_progress_bar=False)[0].tolist()
        raw = self._index.similarity_search(
            query_vector=query_vector,
            columns=RESULT_COLUMNS,
            num_results=k,
        )
        rows = raw.get("result", {}).get("data_array", [])
        results = []
        for row in rows:
            _chunk_id, text, ticker, company, filing_date, accession_number, score = row
            results.append(
                SearchResult(
                    text=text,
                    score=float(score),
                    metadata={
                        "ticker": ticker,
                        "company": company,
                        "filing_date": filing_date,
                        "accession_number": accession_number,
                    },
                )
            )
        return results
