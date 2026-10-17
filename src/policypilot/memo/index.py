"""Offset-aware filing index for memo drafting.

Unlike the POC (which joined words and lost positions), every chunk here remembers its exact
character range and line range in the legacy filing document. That is what lets the Credit
Portal open the filing and highlight a citation at the precise spot it came from.

Local backend: Chroma + sentence-transformers. On Databricks the same chunk rows (with
`start`/`end`/`line_*` columns) live in a Unity Catalog Delta table behind Vector Search.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

from policypilot.config import CHROMA_DIR, EMBEDDING_MODEL

_COLLECTION = "contoso_credit_filings"
TARGET_WORDS = 150  # all-MiniLM-L6-v2 embeds ~256 tokens; keep chunks inside that window


@dataclass
class Chunk:
    chunk_id: str
    filing_id: int
    text: str
    start: int
    end: int
    line_start: int
    line_end: int
    score: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def chunk_document(filing_id: int, text: str, target_words: int = TARGET_WORDS) -> list[Chunk]:
    """Group whole lines into ~target_words chunks, overlapping by one line, keeping offsets."""
    lines = text.split("\n")
    offsets, pos = [], 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1

    chunks: list[Chunk] = []
    i = 0
    while i < len(lines):
        j, words = i, 0
        while j < len(lines) and (words < target_words or j == i):
            words += len(lines[j].split())
            j += 1
        start = offsets[i]
        end = offsets[j - 1] + len(lines[j - 1])
        body = text[start:end]
        if body.strip():
            chunks.append(
                Chunk(
                    chunk_id=f"{filing_id}:{len(chunks)}",
                    filing_id=filing_id,
                    text=body,
                    start=start,
                    end=end,
                    line_start=i + 1,
                    line_end=j,
                )
            )
        if j >= len(lines):
            break
        i = j - 1 if j - 1 > i else j  # one-line overlap keeps sentences that straddle lines
    return chunks


class FilingIndex(Protocol):
    def ensure_indexed(self, filing_id: int, text: str) -> int: ...
    def search(self, query: str, filing_id: int, k: int = 4) -> list[Chunk]: ...
    def overlapping(self, filing_id: int, start: int, end: int) -> list[Chunk]: ...


class ChromaFilingIndex:
    def __init__(self, persist_dir: str | None = None):
        import chromadb
        from sentence_transformers import SentenceTransformer

        self._client = chromadb.PersistentClient(path=persist_dir or str(CHROMA_DIR))
        self._col = self._client.get_or_create_collection(
            _COLLECTION, metadata={"hnsw:space": "cosine"}
        )
        self._embedder = SentenceTransformer(EMBEDDING_MODEL)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return self._embedder.encode(texts, show_progress_bar=False).tolist()

    def is_indexed(self, filing_id: int) -> bool:
        return bool(self._col.get(where={"filing_id": filing_id}, limit=1)["ids"])

    def ensure_indexed(self, filing_id: int, text: str) -> int:
        if self.is_indexed(filing_id):
            return 0
        chunks = chunk_document(filing_id, text)
        for b in range(0, len(chunks), 1000):
            batch = chunks[b : b + 1000]
            self._col.upsert(
                ids=[c.chunk_id for c in batch],
                documents=[c.text for c in batch],
                embeddings=self._embed([c.text for c in batch]),
                metadatas=[
                    {
                        "filing_id": c.filing_id,
                        "start": c.start,
                        "end": c.end,
                        "line_start": c.line_start,
                        "line_end": c.line_end,
                    }
                    for c in batch
                ],
            )
        return len(chunks)

    def _to_chunk(self, cid: str, text: str, meta: dict, score: float = 0.0) -> Chunk:
        return Chunk(
            chunk_id=cid,
            filing_id=int(meta["filing_id"]),
            text=text,
            start=int(meta["start"]),
            end=int(meta["end"]),
            line_start=int(meta["line_start"]),
            line_end=int(meta["line_end"]),
            score=score,
        )

    def search(self, query: str, filing_id: int, k: int = 4) -> list[Chunk]:
        res = self._col.query(
            query_embeddings=self._embed([query]), n_results=k, where={"filing_id": filing_id}
        )
        return [
            self._to_chunk(cid, doc, meta, round(1 - dist, 4))
            for cid, doc, meta, dist in zip(
                res["ids"][0],
                res["documents"][0],
                res["metadatas"][0],
                res["distances"][0],
                strict=False,
            )
        ]

    def overlapping(self, filing_id: int, start: int, end: int) -> list[Chunk]:
        res = self._col.get(
            where={
                "$and": [{"filing_id": filing_id}, {"start": {"$lt": end}}, {"end": {"$gt": start}}]
            }
        )
        return [
            self._to_chunk(cid, doc, meta, 1.0)
            for cid, doc, meta in zip(res["ids"], res["documents"], res["metadatas"], strict=False)
        ]
