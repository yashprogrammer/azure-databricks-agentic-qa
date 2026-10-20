from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import DATABASE_URL

if DATABASE_URL.startswith("sqlite:///"):
    from pathlib import Path

    Path(DATABASE_URL.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Analyst(Base):
    """A Credit Portal user account (the table name predates non-analyst users). This is the
    portal's own entitlement record: the identity provider says who someone is, this table
    says whether they may use the portal and in which role."""

    __tablename__ = "analysts"
    email: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))  # analyst | credit_officer | compliance | admin
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")


class Borrower(Base):
    __tablename__ = "borrowers"
    borrower_id: Mapped[str] = mapped_column(String(12), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    sector: Mapped[str] = mapped_column(String(80))
    relationship_manager: Mapped[str] = mapped_column(String(120))
    exposure_musd: Mapped[float] = mapped_column(Float)
    internal_rating: Mapped[str] = mapped_column(String(40))
    next_review: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="Active")
    cik: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AnalystPortfolio(Base):
    __tablename__ = "analyst_portfolio"
    analyst_email: Mapped[str] = mapped_column(ForeignKey("analysts.email"), primary_key=True)
    borrower_id: Mapped[str] = mapped_column(ForeignKey("borrowers.borrower_id"), primary_key=True)


class Filing(Base):
    __tablename__ = "filings"
    filing_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    borrower_id: Mapped[str] = mapped_column(ForeignKey("borrowers.borrower_id"))
    form_type: Mapped[str] = mapped_column(String(10), default="10-K")
    accession_number: Mapped[str] = mapped_column(String(30), unique=True)
    filing_date: Mapped[date] = mapped_column(Date)
    blob_path: Mapped[str] = mapped_column(String(300))
    size_bytes: Mapped[int] = mapped_column(Integer)
    line_count: Mapped[int] = mapped_column(Integer)
    downloaded_at: Mapped[datetime] = mapped_column(DateTime)


class CreditMemo(Base):
    __tablename__ = "credit_memos"
    memo_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    borrower_id: Mapped[str] = mapped_column(ForeignKey("borrowers.borrower_id"))
    analyst_email: Mapped[str] = mapped_column(ForeignKey("analysts.email"))
    review_year: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="Draft")
    recommendation: Mapped[str] = mapped_column(Text, default="")
    approver_email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class MemoSection(Base):
    __tablename__ = "memo_sections"
    __table_args__ = (UniqueConstraint("memo_id", "section_type"),)
    section_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    memo_id: Mapped[str] = mapped_column(ForeignKey("credit_memos.memo_id"))
    section_type: Mapped[str] = mapped_column(String(40))
    body: Mapped[str] = mapped_column(Text, default="")
    updated_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RestrictedEntry(Base):
    __tablename__ = "restricted_list"
    borrower_id: Mapped[str] = mapped_column(ForeignKey("borrowers.borrower_id"), primary_key=True)
    reason: Mapped[str] = mapped_column(String(300))
    added_by: Mapped[str] = mapped_column(String(120))
    effective_from: Mapped[date] = mapped_column(Date)


class ActivityLog(Base):
    __tablename__ = "activity_log"
    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime)
    actor: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(300))


def init_db() -> None:
    Base.metadata.create_all(engine)
    _migrate()


def _migrate() -> None:
    """Additive schema changes for databases created by earlier releases."""
    columns = {c["name"] for c in inspect(engine).get_columns("analysts")}
    if "active" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE analysts ADD active BOOLEAN NOT NULL DEFAULT 1"))


def get_session():
    """FastAPI dependency: one database session per request."""
    with SessionLocal() as s:
        yield s
