"""VectorStore protocol — swap local_chroma for databricks_vector_search via config,
with no changes needed elsewhere in the codebase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class SearchResult:
    text: str
    score: float
    metadata: dict


class VectorStore(Protocol):
    def upsert(self, ids: list[str], texts: list[str], metadatas: list[dict]) -> None: ...

    def search(self, query: str, k: int = 5) -> list[SearchResult]: ...
