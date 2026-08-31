"""Local dev VectorStore backend: Chroma (on-disk) + sentence-transformers embeddings.
No API key or cloud dependency — this is what runs before a Databricks workspace exists.
"""

from __future__ import annotations

import chromadb
from sentence_transformers import SentenceTransformer

from policypilot.config import CHROMA_DIR, EMBEDDING_MODEL
from policypilot.retrieval.base import SearchResult

_COLLECTION_NAME = "policypilot_filings"


class LocalChromaVectorStore:
    def __init__(self, persist_dir: str | None = None):
        persist_dir = persist_dir or str(CHROMA_DIR)
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(_COLLECTION_NAME)
        self._embedder = SentenceTransformer(EMBEDDING_MODEL)

    def upsert(self, ids: list[str], texts: list[str], metadatas: list[dict]) -> None:
        if not ids:
            return
        embeddings = self._embedder.encode(texts, show_progress_bar=False).tolist()
        self._collection.upsert(
            ids=ids, documents=texts, metadatas=metadatas, embeddings=embeddings
        )

    def search(self, query: str, k: int = 5) -> list[SearchResult]:
        query_embedding = self._embedder.encode([query], show_progress_bar=False).tolist()
        results = self._collection.query(query_embeddings=query_embedding, n_results=k)
        out: list[SearchResult] = []
        docs = results.get("documents") or [[]]
        metas = results.get("metadatas") or [[]]
        dists = results.get("distances") or [[]]
        for text, meta, dist in zip(docs[0], metas[0], dists[0], strict=False):
            out.append(SearchResult(text=text, score=1 - dist, metadata=meta))
        return out

    def count(self) -> int:
        return self._collection.count()
