"""Filing document store. Locally a folder; on Azure this becomes a Blob Storage container
(same relative paths, swap these two functions for azure-storage-blob calls)."""

from __future__ import annotations

from pathlib import Path

from app.config import STORAGE_DIR


def write_document(blob_path: str, text: str) -> int:
    path = STORAGE_DIR / blob_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path.stat().st_size


def read_document(blob_path: str) -> str:
    return (STORAGE_DIR / blob_path).read_text(encoding="utf-8")


def document_exists(blob_path: str) -> bool:
    return Path(STORAGE_DIR / blob_path).exists()
