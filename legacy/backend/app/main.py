"""Contoso Bank Commercial Credit Portal - REST API (v4).

Run locally: `uv run uvicorn app.main:app --port 8100 --reload`
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import MEMO_SECTIONS, SECTION_TYPES
from app.db import (
    ActivityLog,
    Analyst,
    AnalystPortfolio,
    Borrower,
    CreditMemo,
    Filing,
    MemoSection,
    RestrictedEntry,
    SessionLocal,
    init_db,
)
from app.storage import document_exists, read_document

app = FastAPI(title="Contoso Credit Portal API", version="4.2.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


def db():
    with SessionLocal() as s:
        yield s


def _log(s: Session, actor: str, action: str) -> None:
    s.add(ActivityLog(at=datetime.now(), actor=actor, action=action))


def _restricted_ids(s: Session) -> set[str]:
    return set(s.scalars(select(RestrictedEntry.borrower_id)))


def _borrower_row(b: Borrower, restricted: set[str]) -> dict:
    return {
        "borrower_id": b.borrower_id, "ticker": b.ticker, "name": b.name, "sector": b.sector,
        "relationship_manager": b.relationship_manager, "exposure_musd": b.exposure_musd,
        "internal_rating": b.internal_rating, "next_review": b.next_review.isoformat(),
        "status": b.status, "restricted": b.borrower_id in restricted,
    }


def _filing_row(f: Filing, ticker: str | None = None) -> dict:
    return {
        "filing_id": f.filing_id, "borrower_id": f.borrower_id, "ticker": ticker,
        "form_type": f.form_type, "accession_number": f.accession_number,
        "filing_date": f.filing_date.isoformat(), "blob_path": f.blob_path,
        "size_bytes": f.size_bytes, "line_count": f.line_count,
        "downloaded_at": f.downloaded_at.isoformat(timespec="seconds"),
    }


def _memo_row(m: CreditMemo, b: Borrower | None = None) -> dict:
    return {
        "memo_id": m.memo_id, "borrower_id": m.borrower_id,
        "borrower_name": b.name if b else None, "ticker": b.ticker if b else None,
        "analyst_email": m.analyst_email, "review_year": m.review_year, "status": m.status,
        "recommendation": m.recommendation, "approver_email": m.approver_email,
        "created_at": m.created_at.isoformat(timespec="seconds"),
        "updated_at": m.updated_at.isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------- session / reference data

@app.get("/api/users")
def users(s: Session = Depends(db)):
    return [{"email": a.email, "name": a.name, "title": a.title, "role": a.role}
            for a in s.scalars(select(Analyst).order_by(Analyst.name))]


@app.get("/api/memo-template")
def memo_template():
    return [{"section_type": k, "title": t} for k, t in MEMO_SECTIONS]


@app.get("/api/portfolio")
def portfolio(analyst: str, s: Session = Depends(db)):
    return list(s.scalars(select(AnalystPortfolio.borrower_id)
                          .where(AnalystPortfolio.analyst_email == analyst)))


# ---------------------------------------------------------------- dashboard

@app.get("/api/dashboard")
def dashboard(analyst: str, s: Session = Depends(db)):
    my_ids = portfolio(analyst, s)
    restricted = _restricted_ids(s)
    borrowers = s.scalars(select(Borrower).where(Borrower.borrower_id.in_(my_ids))
                          .order_by(Borrower.next_review)).all()
    memo_counts = dict(s.execute(
        select(CreditMemo.status, func.count()).where(CreditMemo.analyst_email == analyst)
        .group_by(CreditMemo.status)).all())
    activity = s.scalars(select(ActivityLog).order_by(ActivityLog.at.desc()).limit(12)).all()
    return {
        "work_queue": [_borrower_row(b, restricted) for b in borrowers],
        "memo_counts": memo_counts,
        "filings_on_file": s.scalar(select(func.count()).select_from(Filing)),
        "activity": [{"at": a.at.isoformat(timespec="minutes"), "actor": a.actor, "action": a.action}
                     for a in activity],
    }


# ---------------------------------------------------------------- borrowers

@app.get("/api/borrowers")
def borrowers(q: str = "", analyst: str | None = None, s: Session = Depends(db)):
    query = select(Borrower).order_by(Borrower.borrower_id)
    if analyst:
        query = query.where(Borrower.borrower_id.in_(portfolio(analyst, s)))
    if q:
        like = f"%{q}%"
        query = query.where(Borrower.name.ilike(like) | Borrower.ticker.ilike(like)
                            | Borrower.borrower_id.ilike(like))
    restricted = _restricted_ids(s)
    return [_borrower_row(b, restricted) for b in s.scalars(query)]


@app.get("/api/borrowers/{borrower_id}")
def borrower(borrower_id: str, s: Session = Depends(db)):
    b = s.get(Borrower, borrower_id)
    if not b:
        raise HTTPException(404, "Borrower not found")
    restricted = s.get(RestrictedEntry, borrower_id)
    analysts = list(s.scalars(select(AnalystPortfolio.analyst_email)
                              .where(AnalystPortfolio.borrower_id == borrower_id)))
    filings = s.scalars(select(Filing).where(Filing.borrower_id == borrower_id)
                        .order_by(Filing.filing_date.desc())).all()
    memos = s.scalars(select(CreditMemo).where(CreditMemo.borrower_id == borrower_id)
                      .order_by(CreditMemo.review_year.desc())).all()
    return {
        **_borrower_row(b, {borrower_id} if restricted else set()),
        "cik": b.cik,
        "restriction": {"reason": restricted.reason, "effective_from": restricted.effective_from.isoformat()}
        if restricted else None,
        "covering_analysts": analysts,
        "filings": [_filing_row(f, b.ticker) for f in filings],
        "memos": [_memo_row(m, b) for m in memos],
    }


# ---------------------------------------------------------------- filings

@app.get("/api/filings")
def filings(borrower_id: str | None = None, s: Session = Depends(db)):
    query = (select(Filing, Borrower.ticker).join(Borrower, Borrower.borrower_id == Filing.borrower_id)
             .order_by(Borrower.ticker, Filing.filing_date.desc()))
    if borrower_id:
        query = query.where(Filing.borrower_id == borrower_id)
    return [_filing_row(f, t) for f, t in s.execute(query)]


@app.get("/api/filings/{filing_id}")
def filing(filing_id: int, s: Session = Depends(db)):
    f = s.get(Filing, filing_id)
    if not f:
        raise HTTPException(404, "Filing not found")
    return _filing_row(f, s.get(Borrower, f.borrower_id).ticker)


@app.get("/api/filings/{filing_id}/text")
def filing_text(filing_id: int, s: Session = Depends(db)):
    f = s.get(Filing, filing_id)
    if not f or not document_exists(f.blob_path):
        raise HTTPException(404, "Document not found in filing store")
    return {"filing_id": filing_id, "text": read_document(f.blob_path)}


# ---------------------------------------------------------------- keyword search

@app.get("/api/search")
def search(q: str = Query(min_length=2), borrower_id: str | None = None,
           limit: int = 200, s: Session = Depends(db)):
    """Legacy keyword search: case-insensitive substring match, line by line."""
    query = select(Filing, Borrower.ticker).join(Borrower, Borrower.borrower_id == Filing.borrower_id)
    if borrower_id:
        query = query.where(Filing.borrower_id == borrower_id)
    needle = q.lower()
    hits: list[dict] = []
    for f, ticker in s.execute(query):
        if not document_exists(f.blob_path):
            continue
        for line_no, line in enumerate(read_document(f.blob_path).splitlines(), start=1):
            if needle in line.lower():
                hits.append({"filing_id": f.filing_id, "ticker": ticker,
                             "accession_number": f.accession_number, "line": line_no,
                             "snippet": line[:300]})
                if len(hits) >= limit:
                    return {"query": q, "truncated": True, "hits": hits}
    return {"query": q, "truncated": False, "hits": hits}


# ---------------------------------------------------------------- credit memos

class NewMemo(BaseModel):
    borrower_id: str
    analyst_email: str


class SectionUpdate(BaseModel):
    body: str
    updated_by: str


class RecommendationUpdate(BaseModel):
    recommendation: str
    updated_by: str


class Decision(BaseModel):
    actor: str


@app.get("/api/memos")
def memos(analyst: str | None = None, status: str | None = None, s: Session = Depends(db)):
    query = (select(CreditMemo, Borrower).join(Borrower, Borrower.borrower_id == CreditMemo.borrower_id)
             .order_by(CreditMemo.review_year.desc(), CreditMemo.memo_id))
    if analyst:
        query = query.where(CreditMemo.analyst_email == analyst)
    if status:
        query = query.where(CreditMemo.status == status)
    return [_memo_row(m, b) for m, b in s.execute(query)]


@app.post("/api/memos")
def create_memo(body: NewMemo, s: Session = Depends(db)):
    if not s.get(Borrower, body.borrower_id):
        raise HTTPException(404, "Borrower not found")
    year = date.today().year
    seq = s.scalar(select(func.count()).select_from(CreditMemo)
                   .where(CreditMemo.review_year == year)) + 101
    memo_id = f"CM-{year}-{seq:04d}"
    now = datetime.now()
    s.add(CreditMemo(memo_id=memo_id, borrower_id=body.borrower_id, analyst_email=body.analyst_email,
                     review_year=year, status="Draft", created_at=now, updated_at=now))
    s.flush()
    for section_type in SECTION_TYPES:
        s.add(MemoSection(memo_id=memo_id, section_type=section_type, body=""))
    _log(s, body.analyst_email, f"Created credit memo {memo_id} for {body.borrower_id}")
    s.commit()
    return {"memo_id": memo_id}


@app.get("/api/memos/{memo_id}")
def memo(memo_id: str, s: Session = Depends(db)):
    m = s.get(CreditMemo, memo_id)
    if not m:
        raise HTTPException(404, "Memo not found")
    b = s.get(Borrower, m.borrower_id)
    sections = {sec.section_type: sec for sec in
                s.scalars(select(MemoSection).where(MemoSection.memo_id == memo_id))}
    return {
        **_memo_row(m, b),
        "sections": [
            {"section_type": k, "title": t,
             "body": sections[k].body if k in sections else "",
             "updated_by": sections[k].updated_by if k in sections else None,
             "updated_at": sections[k].updated_at.isoformat(timespec="seconds")
             if k in sections and sections[k].updated_at else None}
            for k, t in MEMO_SECTIONS
        ],
    }


def _editable_memo(s: Session, memo_id: str) -> CreditMemo:
    m = s.get(CreditMemo, memo_id)
    if not m:
        raise HTTPException(404, "Memo not found")
    if m.status not in ("Draft", "Returned"):
        raise HTTPException(409, f"Memo is {m.status} and can no longer be edited")
    return m


@app.put("/api/memos/{memo_id}/sections/{section_type}")
def update_section(memo_id: str, section_type: str, body: SectionUpdate, s: Session = Depends(db)):
    if section_type not in SECTION_TYPES:
        raise HTTPException(404, "Unknown section")
    m = _editable_memo(s, memo_id)
    sec = s.scalar(select(MemoSection).where(MemoSection.memo_id == memo_id,
                                             MemoSection.section_type == section_type))
    if not sec:
        sec = MemoSection(memo_id=memo_id, section_type=section_type)
        s.add(sec)
    sec.body, sec.updated_by, sec.updated_at = body.body, body.updated_by, datetime.now()
    m.updated_at = datetime.now()
    _log(s, body.updated_by, f"Updated section '{section_type}' of {memo_id}")
    s.commit()
    return {"ok": True}


@app.put("/api/memos/{memo_id}/recommendation")
def update_recommendation(memo_id: str, body: RecommendationUpdate, s: Session = Depends(db)):
    m = _editable_memo(s, memo_id)
    m.recommendation, m.updated_at = body.recommendation, datetime.now()
    _log(s, body.updated_by, f"Updated recommendation of {memo_id}")
    s.commit()
    return {"ok": True}


def _transition(s: Session, memo_id: str, actor: str, allowed: tuple[str, ...], new: str) -> dict:
    m = s.get(CreditMemo, memo_id)
    if not m:
        raise HTTPException(404, "Memo not found")
    if m.status not in allowed:
        raise HTTPException(409, f"Cannot move memo from {m.status} to {new}")
    m.status, m.updated_at = new, datetime.now()
    if new == "Approved":
        m.approver_email = actor
    _log(s, actor, f"Memo {memo_id} -> {new}")
    s.commit()
    return {"ok": True, "status": new}


@app.post("/api/memos/{memo_id}/submit")
def submit(memo_id: str, body: Decision, s: Session = Depends(db)):
    return _transition(s, memo_id, body.actor, ("Draft", "Returned"), "Submitted")


@app.post("/api/memos/{memo_id}/approve")
def approve(memo_id: str, body: Decision, s: Session = Depends(db)):
    return _transition(s, memo_id, body.actor, ("Submitted",), "Approved")


@app.post("/api/memos/{memo_id}/return")
def return_memo(memo_id: str, body: Decision, s: Session = Depends(db)):
    return _transition(s, memo_id, body.actor, ("Submitted",), "Returned")


# ---------------------------------------------------------------- compliance

@app.get("/api/restricted")
def restricted(s: Session = Depends(db)):
    rows = s.execute(select(RestrictedEntry, Borrower)
                     .join(Borrower, Borrower.borrower_id == RestrictedEntry.borrower_id)).all()
    return [{"borrower_id": r.borrower_id, "ticker": b.ticker, "name": b.name, "reason": r.reason,
             "added_by": r.added_by, "effective_from": r.effective_from.isoformat()}
            for r, b in rows]
