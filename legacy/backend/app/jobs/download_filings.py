"""Nightly filing downloader. For every active borrower, fetch the latest 10-K from SEC EDGAR,
convert it to plain text, store it in the filing store and register it in `filings`.

Locally: `uv run python -m app.jobs.download_filings` (add tickers to limit: `... AAPL MSFT`).
On Azure this same function runs inside an Azure Function on a nightly timer trigger.
"""

from __future__ import annotations

import sys
import time
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup
from sqlalchemy import select

from app.config import SEC_USER_AGENT
from app.db import ActivityLog, Borrower, Filing, SessionLocal, init_db
from app.storage import write_document

_session = requests.Session()
_session.headers.update({"User-Agent": SEC_USER_AGENT})


def _get(url: str) -> requests.Response:
    resp = _session.get(url, timeout=60)
    resp.raise_for_status()
    time.sleep(0.15)  # stay well under SEC's 10 requests/second fair-access limit
    return resp


def _ticker_to_cik() -> dict[str, int]:
    data = _get("https://www.sec.gov/files/company_tickers.json").json()
    return {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}


def _latest_10k(cik: int) -> dict | None:
    recent = _get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()["filings"]["recent"]
    for i, form in enumerate(recent["form"]):
        if form == "10-K":
            return {
                "accession_number": recent["accessionNumber"][i],
                "primary_document": recent["primaryDocument"][i],
                "filing_date": recent["filingDate"][i],
            }
    return None


def _to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    lines = (line.strip() for line in soup.get_text(separator="\n").splitlines())
    return "\n".join(line for line in lines if line)


def run(tickers: list[str] | None = None) -> int:
    init_db()
    ciks = _ticker_to_cik()
    downloaded = 0
    with SessionLocal() as s:
        query = select(Borrower).where(Borrower.status == "Active")
        if tickers:
            query = query.where(Borrower.ticker.in_([t.upper() for t in tickers]))
        for borrower in s.scalars(query):
            cik = borrower.cik or ciks.get(borrower.ticker)
            if not cik:
                print(f"{borrower.ticker}: no CIK found, skipped")
                continue
            borrower.cik = cik
            filing = _latest_10k(cik)
            if not filing:
                print(f"{borrower.ticker}: no 10-K found, skipped")
                continue
            if s.scalar(select(Filing).where(Filing.accession_number == filing["accession_number"])):
                print(f"{borrower.ticker}: {filing['accession_number']} already stored")
                continue
            nodash = filing["accession_number"].replace("-", "")
            html = _get(
                f"https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/{filing['primary_document']}"
            ).text
            text = _to_text(html)
            blob_path = f"{borrower.ticker}/{filing['accession_number']}.txt"
            size = write_document(blob_path, text)
            s.add(Filing(
                borrower_id=borrower.borrower_id,
                accession_number=filing["accession_number"],
                filing_date=date.fromisoformat(filing["filing_date"]),
                blob_path=blob_path,
                size_bytes=size,
                line_count=text.count("\n") + 1,
                downloaded_at=datetime.now(),
            ))
            s.add(ActivityLog(at=datetime.now(), actor="nightly-job",
                              action=f"Downloaded 10-K {filing['accession_number']} for {borrower.ticker}"))
            s.commit()
            downloaded += 1
            print(f"{borrower.ticker}: stored {filing['accession_number']} ({size:,} bytes)")
    print(f"Done: {downloaded} new filing(s).")
    return downloaded


if __name__ == "__main__":
    run(sys.argv[1:] or None)
