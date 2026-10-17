"""Seed the Credit Portal with Contoso Bank's (fictional) analysts, borrowers, portfolios,
restricted list and this year's open review memos. Filings are NOT seeded here: the nightly
downloader job (`python -m app.jobs.download_filings`) fetches them from SEC EDGAR.

Run: `uv run python -m app.seed` (add `--reset` to wipe and recreate the database).
"""

from __future__ import annotations

import sys
from datetime import date, datetime

from app.config import SECTION_TYPES
from app.db import (
    ActivityLog,
    Analyst,
    AnalystPortfolio,
    Base,
    Borrower,
    CreditMemo,
    MemoSection,
    RestrictedEntry,
    SessionLocal,
    engine,
)

ANALYSTS = [
    ("m.lee@contoso.example", "Marcus Lee", "Lead Credit Analyst", "analyst"),
    ("a.ruiz@contoso.example", "Ana Ruiz", "Credit Analyst", "analyst"),
    ("d.cho@contoso.example", "Daniel Cho", "Credit Analyst", "analyst"),
    ("p.raman@contoso.example", "Priya Raman", "Chief Credit Officer", "credit_officer"),
    ("a.karim@contoso.example", "Aisha Karim", "Compliance Officer", "compliance"),
]

# borrower_id, ticker, name, sector, relationship manager, exposure ($M), rating, next review
BORROWERS = [
    ("B-1001", "AAPL", "Apple Inc.", "Technology Hardware", "J. Whitmore", 750.0, "2 - Strong", date(2026, 11, 14)),
    ("B-1002", "MSFT", "Microsoft Corporation", "Software", "J. Whitmore", 900.0, "1 - Excellent", date(2026, 11, 21)),
    ("B-1003", "NVDA", "NVIDIA Corporation", "Semiconductors", "R. Okoye", 420.0, "3 - Good", date(2026, 12, 5)),
    ("B-1004", "CSCO", "Cisco Systems, Inc.", "Networking Equipment", "R. Okoye", 310.0, "3 - Good", date(2027, 1, 9)),
    ("B-1005", "INTC", "Intel Corporation", "Semiconductors", "R. Okoye", 380.0, "5 - Acceptable", date(2026, 10, 30)),
    ("B-1006", "GOOGL", "Alphabet Inc.", "Interactive Media", "J. Whitmore", 650.0, "2 - Strong", date(2027, 2, 12)),
    ("B-1007", "META", "Meta Platforms, Inc.", "Interactive Media", "L. Brennan", 540.0, "3 - Good", date(2027, 2, 20)),
    ("B-1008", "JPM", "JPMorgan Chase & Co.", "Diversified Banks", "S. Haddad", 500.0, "2 - Strong", date(2026, 12, 12)),
    ("B-1009", "BAC", "Bank of America Corporation", "Diversified Banks", "S. Haddad", 450.0, "3 - Good", date(2027, 1, 16)),
    ("B-1010", "V", "Visa Inc.", "Payments", "S. Haddad", 300.0, "2 - Strong", date(2026, 11, 28)),
    ("B-1011", "JNJ", "Johnson & Johnson", "Pharmaceuticals", "M. Adeyemi", 520.0, "2 - Strong", date(2027, 3, 6)),
    ("B-1012", "PG", "The Procter & Gamble Company", "Household Products", "M. Adeyemi", 360.0, "2 - Strong", date(2027, 3, 13)),
    ("B-1013", "KO", "The Coca-Cola Company", "Beverages", "M. Adeyemi", 330.0, "3 - Good", date(2027, 2, 27)),
    ("B-1014", "PEP", "PepsiCo, Inc.", "Beverages", "M. Adeyemi", 340.0, "3 - Good", date(2027, 3, 20)),
    ("B-1015", "AMZN", "Amazon.com, Inc.", "Broadline Retail", "L. Brennan", 800.0, "2 - Strong", date(2026, 12, 19)),
    ("B-1016", "WMT", "Walmart Inc.", "Consumer Staples Retail", "L. Brennan", 610.0, "2 - Strong", date(2026, 11, 7)),
    ("B-1017", "HD", "The Home Depot, Inc.", "Home Improvement Retail", "L. Brennan", 400.0, "3 - Good", date(2027, 1, 30)),
    ("B-1018", "CVX", "Chevron Corporation", "Integrated Oil & Gas", "T. Varga", 470.0, "3 - Good", date(2027, 2, 6)),
    ("B-1019", "DIS", "The Walt Disney Company", "Entertainment", "T. Varga", 390.0, "4 - Satisfactory", date(2026, 12, 26)),
    ("B-1020", "TSLA", "Tesla, Inc.", "Automobiles", "T. Varga", 280.0, "4 - Satisfactory", date(2027, 1, 23)),
]

PORTFOLIOS = {
    "m.lee@contoso.example": ["B-1001", "B-1002", "B-1003", "B-1004", "B-1005", "B-1006", "B-1007"],
    "a.ruiz@contoso.example": ["B-1008", "B-1009", "B-1010", "B-1011", "B-1012", "B-1013", "B-1014"],
    "d.cho@contoso.example": ["B-1015", "B-1016", "B-1017", "B-1018", "B-1019", "B-1020"],
}

RESTRICTED = [
    ("B-1020", ("Investment Banking advisory mandate in progress. Information barrier: credit "
                "research suspended until cleared by Compliance."), date(2026, 9, 2)),
    ("B-1007", ("Pending syndicated facility. Material non-public information received by "
                "Corporate Banking."), date(2026, 9, 18)),
]

# memo_id, borrower_id, analyst, review year, status
MEMOS = [
    ("CM-2025-0412", "B-1001", "m.lee@contoso.example", 2025, "Approved"),
    ("CM-2025-0419", "B-1008", "a.ruiz@contoso.example", 2025, "Approved"),
    ("CM-2026-0101", "B-1001", "m.lee@contoso.example", 2026, "Draft"),
    ("CM-2026-0102", "B-1002", "m.lee@contoso.example", 2026, "Draft"),
    ("CM-2026-0103", "B-1008", "a.ruiz@contoso.example", 2026, "Draft"),
    ("CM-2026-0104", "B-1016", "d.cho@contoso.example", 2026, "Draft"),
]

ARCHIVED_NOTE = "[Archived] Migrated from Credit System v3. Full text in the 2025 scanned review file."


def seed(reset: bool = False) -> None:
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    now = datetime.now()
    with SessionLocal() as s:
        if s.get(Analyst, ANALYSTS[0][0]):
            print("Database already seeded (use --reset to recreate).")
            return
        s.add_all(Analyst(email=e, name=n, title=t, role=r) for e, n, t, r in ANALYSTS)
        s.add_all(
            Borrower(borrower_id=b, ticker=t, name=n, sector=sec, relationship_manager=rm,
                     exposure_musd=x, internal_rating=r, next_review=nr)
            for b, t, n, sec, rm, x, r, nr in BORROWERS
        )
        s.flush()
        s.add_all(
            AnalystPortfolio(analyst_email=a, borrower_id=b)
            for a, ids in PORTFOLIOS.items() for b in ids
        )
        s.add_all(
            RestrictedEntry(borrower_id=b, reason=r, added_by="a.karim@contoso.example",
                            effective_from=d)
            for b, r, d in RESTRICTED
        )
        for memo_id, borrower_id, analyst, year, status in MEMOS:
            approved = status == "Approved"
            s.add(CreditMemo(
                memo_id=memo_id, borrower_id=borrower_id, analyst_email=analyst,
                review_year=year, status=status,
                recommendation="Renew facility at existing terms." if approved else "",
                approver_email="p.raman@contoso.example" if approved else None,
                created_at=now, updated_at=now,
            ))
            s.flush()
            for section_type in SECTION_TYPES:
                s.add(MemoSection(
                    memo_id=memo_id, section_type=section_type,
                    body=ARCHIVED_NOTE if approved else "",
                    updated_by=analyst if approved else None,
                    updated_at=now if approved else None,
                ))
        s.add(ActivityLog(at=now, actor="system", action="Credit Portal database initialised"))
        s.commit()
    print(f"Seeded {len(ANALYSTS)} users, {len(BORROWERS)} borrowers, {len(MEMOS)} memos.")


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
