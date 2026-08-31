"""Agent tools. `retrieve` hits the unstructured filing corpus (VectorStore); `filing_metadata`
answers structured lookups (filed-on-date, accession number) — in production this becomes a
UC function so the query planner can route between them, per the architecture doc.
"""

from __future__ import annotations

from policypilot.ingestion.manifest import load_manifest
from policypilot.retrieval.base import SearchResult, VectorStore


def retrieve(store: VectorStore, query: str, k: int = 5) -> list[SearchResult]:
    return store.search(query, k=k)


def filing_metadata(ticker: str) -> dict | None:
    return load_manifest().get(ticker.upper())


def format_context(results: list[SearchResult]) -> str:
    """Render retrieved chunks as a numbered, citable context block."""
    blocks = []
    for i, r in enumerate(results, start=1):
        m = r.metadata
        blocks.append(
            f"[{i}] {m.get('company')} 10-K (filed {m.get('filing_date')}, "
            f"accession {m.get('accession_number')}):\n{r.text}"
        )
    return "\n\n".join(blocks)
