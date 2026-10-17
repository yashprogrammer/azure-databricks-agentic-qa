"""Version store for AI memo drafts (the AI service's own database, separate from the legacy
Credit Portal database).

Every change to a section, whether an AI run, an analyst edit or a restore, appends an immutable
version. Nothing is ever overwritten, which is what gives analysts "time travel" and gives
Model Risk Management a full audit trail. Locally SQLite; on Azure a small Azure SQL /
Lakebase database or a Delta table.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from policypilot.config import DATA_DIR

DB_PATH = Path(os.environ.get("MEMO_AI_DB", DATA_DIR / "memo_ai.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    memo_id TEXT PRIMARY KEY, borrower_id TEXT, ticker TEXT, analyst_email TEXT,
    filing_id INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS versions (
    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
    memo_id TEXT, section_type TEXT, version_no INTEGER,
    origin TEXT,                -- ai | human | restore
    text TEXT, citations TEXT, reasoning TEXT, trace TEXT,
    feedback TEXT, quotes TEXT, based_on INTEGER,
    grounded INTEGER, refusal_reason TEXT, warnings TEXT,
    created_by TEXT, created_at TEXT,
    UNIQUE (memo_id, section_type, version_no)
);
CREATE TABLE IF NOT EXISTS section_state (
    memo_id TEXT, section_type TEXT,
    current_version INTEGER, approved_version INTEGER,
    saved_version INTEGER, saved_at TEXT,
    PRIMARY KEY (memo_id, section_type)
);
CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    memo_id TEXT, section_type TEXT, actor TEXT, action TEXT, detail TEXT, at TEXT
);
"""

_JSON_FIELDS = ("citations", "trace", "quotes", "warnings")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class DraftStore:
    def __init__(self, path: Path | str = DB_PATH):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._db.executescript(_SCHEMA)

    # ---------------------------------------------------------------- drafts
    def ensure_draft(
        self, memo_id: str, borrower_id: str, ticker: str, analyst: str, filing_id: int | None
    ) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO drafts VALUES (?,?,?,?,?,?)",
                (memo_id, borrower_id, ticker, analyst, filing_id, _now()),
            )

    # ---------------------------------------------------------------- versions
    def add_version(
        self,
        memo_id: str,
        section_type: str,
        *,
        origin: str,
        text: str,
        created_by: str,
        citations: list | None = None,
        reasoning: str = "",
        trace: dict | None = None,
        feedback: str = "",
        quotes: list | None = None,
        based_on: int | None = None,
        grounded: bool = False,
        refusal_reason: str | None = None,
        warnings: list | None = None,
    ) -> dict:
        with self._lock, self._db:
            n = self._db.execute(
                "SELECT COALESCE(MAX(version_no), 0) + 1 FROM versions"
                " WHERE memo_id=? AND section_type=?",
                (memo_id, section_type),
            ).fetchone()[0]
            self._db.execute(
                """INSERT INTO versions (memo_id, section_type, version_no, origin, text, citations,
                   reasoning, trace, feedback, quotes, based_on, grounded, refusal_reason, warnings,
                   created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    memo_id,
                    section_type,
                    n,
                    origin,
                    text,
                    json.dumps(citations or []),
                    reasoning,
                    json.dumps(trace or {}),
                    feedback,
                    json.dumps(quotes or []),
                    based_on,
                    int(grounded),
                    refusal_reason,
                    json.dumps(warnings or []),
                    created_by,
                    _now(),
                ),
            )
            self._db.execute(
                """INSERT INTO section_state (memo_id, section_type, current_version) VALUES (?,?,?)
                   ON CONFLICT (memo_id, section_type)
                   DO UPDATE SET current_version=excluded.current_version""",
                (memo_id, section_type, n),
            )
            self._event(
                memo_id, section_type, created_by, f"version {n} created ({origin})", feedback
            )
        return self.version(memo_id, section_type, n)

    def version(self, memo_id: str, section_type: str, version_no: int) -> dict | None:
        row = self._db.execute(
            "SELECT * FROM versions WHERE memo_id=? AND section_type=? AND version_no=?",
            (memo_id, section_type, version_no),
        ).fetchone()
        return self._decode(row) if row else None

    def versions(self, memo_id: str, section_type: str) -> list[dict]:
        rows = self._db.execute(
            """SELECT version_no, origin, grounded, refusal_reason, feedback, based_on, created_by,
                      created_at FROM versions
               WHERE memo_id=? AND section_type=? ORDER BY version_no""",
            (memo_id, section_type),
        ).fetchall()
        return [dict(r) | {"grounded": bool(r["grounded"])} for r in rows]

    # ---------------------------------------------------------------- state / workflow
    def state(self, memo_id: str, section_type: str) -> dict:
        row = self._db.execute(
            "SELECT * FROM section_state WHERE memo_id=? AND section_type=?",
            (memo_id, section_type),
        ).fetchone()
        return (
            dict(row)
            if row
            else {
                "current_version": None,
                "approved_version": None,
                "saved_version": None,
                "saved_at": None,
            }
        )

    def set_current(self, memo_id: str, section_type: str, version_no: int, actor: str) -> None:
        self._require(memo_id, section_type, version_no)
        with self._lock, self._db:
            self._db.execute(
                "UPDATE section_state SET current_version=? WHERE memo_id=? AND section_type=?",
                (version_no, memo_id, section_type),
            )
            self._event(memo_id, section_type, actor, f"switched to version {version_no}")

    def approve(self, memo_id: str, section_type: str, version_no: int, actor: str) -> None:
        self._require(memo_id, section_type, version_no)
        with self._lock, self._db:
            self._db.execute(
                "UPDATE section_state SET approved_version=?, current_version=?"
                " WHERE memo_id=? AND section_type=?",
                (version_no, version_no, memo_id, section_type),
            )
            self._event(memo_id, section_type, actor, f"approved version {version_no}")

    def mark_saved(self, memo_id: str, section_type: str, version_no: int, actor: str) -> None:
        self._require(memo_id, section_type, version_no)
        with self._lock, self._db:
            self._db.execute(
                "UPDATE section_state SET saved_version=?, saved_at=?"
                " WHERE memo_id=? AND section_type=?",
                (version_no, _now(), memo_id, section_type),
            )
            self._event(
                memo_id, section_type, actor, f"saved version {version_no} to the credit memo"
            )

    def log(
        self, memo_id: str, section_type: str, actor: str, action: str, detail: str = ""
    ) -> None:
        with self._lock, self._db:
            self._event(memo_id, section_type, actor, action, detail)

    def events(self, memo_id: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM events WHERE memo_id=? ORDER BY event_id DESC LIMIT 200", (memo_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- helpers
    def _require(self, memo_id: str, section_type: str, version_no: int) -> None:
        if not self.version(memo_id, section_type, version_no):
            raise KeyError(f"version {version_no} not found")

    def _event(
        self, memo_id: str, section_type: str, actor: str, action: str, detail: str = ""
    ) -> None:
        self._db.execute(
            "INSERT INTO events (memo_id, section_type, actor, action, detail, at)"
            " VALUES (?,?,?,?,?,?)",
            (memo_id, section_type, actor, action, detail, _now()),
        )

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict:
        d = dict(row)
        for f in _JSON_FIELDS:
            d[f] = json.loads(d[f] or ("{}" if f == "trace" else "[]"))
        d["grounded"] = bool(d["grounded"])
        return d
