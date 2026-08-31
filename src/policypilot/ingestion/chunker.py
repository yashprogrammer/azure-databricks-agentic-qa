"""Splits filing text into overlapping, citation-friendly chunks."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Chunk:
    id: str
    text: str
    ticker: str
    company: str
    filing_date: str
    accession_number: str
    chunk_index: int
    metadata: dict = field(default_factory=dict)


def _split_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(words):
        window = words[start : start + chunk_size]
        chunks.append(" ".join(window))
        if start + chunk_size >= len(words):
            break
        start += chunk_size - overlap
    return chunks


def chunk_filing(ticker: str, filing: dict, text: str) -> list[Chunk]:
    raw_chunks = _split_text(text)
    company = filing["company"]
    filing_date = filing["filing_date"]
    accession_number = filing["accession_number"]
    return [
        Chunk(
            id=f"{ticker}-{accession_number}-{i}",
            text=raw,
            ticker=ticker,
            company=company,
            filing_date=filing_date,
            accession_number=accession_number,
            chunk_index=i,
        )
        for i, raw in enumerate(raw_chunks)
    ]
