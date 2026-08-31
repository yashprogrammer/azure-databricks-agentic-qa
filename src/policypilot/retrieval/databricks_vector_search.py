"""Production VectorStore backend: Databricks Vector Search over a Delta-synced UC table.

Stubbed until a workspace + Unity Catalog metastore exist. Implement once we have:
  - a UC catalog/schema/volume (see scripts/setup_unity_catalog.py)
  - a Delta table of filing chunks with a Change Data Feed
  - a Vector Search endpoint + Delta-sync index over that table

Fill this in with the databricks-vector-search / databricks-sdk clients so it satisfies
the same VectorStore protocol as LocalChromaVectorStore — no other code should need to
change when PP_ENV switches from "local" to "databricks".
"""

from __future__ import annotations

from policypilot.retrieval.base import SearchResult


class DatabricksVectorSearchStore:
    def __init__(self, *, endpoint_name: str, index_name: str):
        raise NotImplementedError(
            "DatabricksVectorSearchStore requires a provisioned Databricks workspace and "
            "Vector Search endpoint. See README 'Next steps' for the provisioning checklist, "
            "then implement this class against the databricks-vector-search SDK."
        )

    def upsert(self, ids: list[str], texts: list[str], metadatas: list[dict]) -> None:
        raise NotImplementedError

    def search(self, query: str, k: int = 5) -> list[SearchResult]:
        raise NotImplementedError
