"""Runtime settings. Locally everything points at files on disk; on Azure the same
variables point at Azure SQL and Blob Storage (see legacy/README.md)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Local: SQLite file. Azure: an Azure SQL connection string, e.g.
# mssql+pyodbc://<user>:<pwd>@<server>.database.windows.net/<db>?driver=ODBC+Driver+18+for+SQL+Server
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'data' / 'contoso.db'}")

# Local: a folder standing in for the Blob Storage container that holds 10-K documents.
STORAGE_DIR = Path(os.environ.get("STORAGE_DIR", BACKEND_DIR / "storage" / "filings"))

# SEC requires a real contact in the User-Agent of every EDGAR request.
SEC_USER_AGENT = os.environ.get(
    "SEC_USER_AGENT", "Contoso Bank Credit Portal credit-ops@contoso.example"
)

# Six fixed sections of the bank's credit memo template (order matters: it's the template).
MEMO_SECTIONS: list[tuple[str, str]] = [
    ("business_overview", "1. Business Overview"),
    ("industry_competition", "2. Industry & Competitive Position"),
    ("financial_performance", "3. Financial Performance"),
    ("liquidity_debt", "4. Liquidity & Debt Structure"),
    ("key_risks", "5. Key Risk Factors"),
    ("legal_regulatory", "6. Legal & Regulatory Matters"),
]
SECTION_TYPES = [key for key, _ in MEMO_SECTIONS]
