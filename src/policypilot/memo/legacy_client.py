"""Read-only client for the legacy Credit Portal API.

The integration only ever READS from the legacy system (borrowers, filings, restricted list,
analyst portfolios), and always as the signed-in user: the user's own bearer token is
forwarded, so the legacy API applies that user's permissions. Writes to the credit memo stay
with the portal itself, which keeps the legacy system the single system of record. On Azure
the same reads come from Azure SQL via Lakehouse Federation and from Blob Storage.
"""

from __future__ import annotations

import os
from typing import Protocol

import requests

LEGACY_API_URL = os.environ.get("LEGACY_API_URL", "http://localhost:8100")


class LegacyPortal(Protocol):
    def memo(self, memo_id: str) -> dict: ...
    def borrower(self, borrower_id: str) -> dict: ...
    def filing_text(self, filing_id: int) -> str: ...
    def restricted_ids(self) -> set[str]: ...
    def portfolio(self) -> set[str]: ...  # the signed-in user's portfolio


class LegacyApiClient:
    def __init__(self, token: str, base_url: str = LEGACY_API_URL):
        self._base = base_url.rstrip("/")
        self._http = requests.Session()
        self._http.headers["Authorization"] = f"Bearer {token}"

    def _get(self, path: str, **params):
        resp = self._http.get(f"{self._base}{path}", params=params or None, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def memo(self, memo_id: str) -> dict:
        return self._get(f"/api/memos/{memo_id}")

    def borrower(self, borrower_id: str) -> dict:
        return self._get(f"/api/borrowers/{borrower_id}")

    def filing_text(self, filing_id: int) -> str:
        return self._get(f"/api/filings/{filing_id}/text")["text"]

    def restricted_ids(self) -> set[str]:
        return {row["borrower_id"] for row in self._get("/api/restricted")}

    def portfolio(self) -> set[str]:
        return set(self._get("/api/portfolio"))
