"""Thin client for SEC EDGAR's public JSON/HTML APIs. No auth required, but SEC's
fair-access policy requires a descriptive User-Agent with a real contact on every request.
"""

from __future__ import annotations

import time

import requests
from bs4 import BeautifulSoup

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{document}"


class EdgarClient:
    def __init__(self, user_agent: str):
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent})

    def _get(self, url: str) -> requests.Response:
        resp = self._session.get(url, timeout=30)
        resp.raise_for_status()
        time.sleep(0.15)  # stay well under SEC's request-rate guidance
        return resp

    def get_cik_for_ticker(self, ticker: str) -> int:
        data = self._get(TICKERS_URL).json()
        ticker = ticker.upper()
        for entry in data.values():
            if entry["ticker"] == ticker:
                return int(entry["cik_str"])
        raise ValueError(f"No CIK found for ticker {ticker!r}")

    def get_recent_10k(self, cik: int) -> dict:
        """Return metadata for the most recent 10-K filing for a company."""
        data = self._get(SUBMISSIONS_URL.format(cik=cik)).json()
        recent = data["filings"]["recent"]
        for i, form in enumerate(recent["form"]):
            if form == "10-K":
                return {
                    "cik": cik,
                    "accession_number": recent["accessionNumber"][i],
                    "primary_document": recent["primaryDocument"][i],
                    "filing_date": recent["filingDate"][i],
                    "company": data.get("name", str(cik)),
                }
        raise ValueError(f"No 10-K found in recent filings for CIK {cik}")

    def download_filing_text(self, filing: dict) -> str:
        """Download a filing's primary document and return its extracted plain text."""
        accession_nodash = filing["accession_number"].replace("-", "")
        url = ARCHIVES_URL.format(
            cik=filing["cik"],
            accession_nodash=accession_nodash,
            document=filing["primary_document"],
        )
        html = self._get(url).text
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)
