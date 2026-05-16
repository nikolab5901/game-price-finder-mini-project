"""SQLite persistence for user-submitted catalog / pricing feedback."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


def _utc_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  category TEXT NOT NULL,
  game_title TEXT,
  reference_note TEXT,
  suggested_price_usd REAL,
  body TEXT NOT NULL,
  contact_email TEXT,
  honeypot INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback (created_at DESC);
"""


def init_feedback_db(db_path: str) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def insert_feedback(
    *,
    db_path: str,
    category: str,
    body: str,
    game_title: str | None,
    reference_note: str | None,
    suggested_price_usd: float | None,
    contact_email: str | None,
    honeypot_filled: bool,
) -> None:
    init_feedback_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO feedback (
              created_at, category, game_title, reference_note,
              suggested_price_usd, body, contact_email, honeypot
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _utc_iso(),
                category,
                game_title.strip()[:300] if game_title else None,
                reference_note.strip()[:800] if reference_note else None,
                suggested_price_usd,
                body.strip()[:8000],
                contact_email.strip()[:200] if contact_email else None,
                1 if honeypot_filled else 0,
            ),
        )
        conn.commit()
    finally:
        conn.close()


@dataclass
class FeedbackRow:
    id: int
    created_at: str
    category: str
    game_title: str | None
    reference_note: str | None
    suggested_price_usd: float | None
    body: str
    contact_email: str | None
    honeypot: int


def list_feedback_recent(*, db_path: str, limit: int = 100) -> list[FeedbackRow]:
    init_feedback_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            """SELECT id, created_at, category, game_title, reference_note,
                      suggested_price_usd, body, contact_email, honeypot
               FROM feedback ORDER BY datetime(created_at) DESC LIMIT ?""",
            (limit,),
        )
        rows = []
        for r in cur.fetchall():
            rows.append(
                FeedbackRow(
                    id=int(r[0]),
                    created_at=str(r[1]),
                    category=str(r[2]),
                    game_title=r[3],
                    reference_note=r[4],
                    suggested_price_usd=float(r[5]) if r[5] is not None else None,
                    body=str(r[6]),
                    contact_email=r[7],
                    honeypot=int(r[8]),
                ),
            )
        return rows
    finally:
        conn.close()
