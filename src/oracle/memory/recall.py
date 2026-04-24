"""Recall memory — SQLite log of every turn + FTS5 keyword search.

Used for: 'what did we talk about yesterday?', 'recall where we left off on
the Celestara project', etc. Much faster than vector search for recent stuff.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from oracle.config import settings


class RecallMemory:
    """SQLite + FTS5 for recent turn-level recall."""

    def __init__(self, path: Path | None = None):
        self.path = path or (settings.oracle_home / "memory" / "recall.sqlite")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        c = self._conn.cursor()
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS turns (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          REAL    NOT NULL,
                thread_id   TEXT    NOT NULL,
                role        TEXT    NOT NULL,
                content     TEXT    NOT NULL,
                meta        TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_turns_thread ON turns(thread_id, ts);
            CREATE INDEX IF NOT EXISTS idx_turns_ts     ON turns(ts);

            CREATE VIRTUAL TABLE IF NOT EXISTS turns_fts USING fts5(
                content, thread_id UNINDEXED, content=turns, content_rowid=id
            );
            CREATE TRIGGER IF NOT EXISTS turns_ai AFTER INSERT ON turns BEGIN
              INSERT INTO turns_fts(rowid, content, thread_id)
                VALUES (new.id, new.content, new.thread_id);
            END;
            CREATE TRIGGER IF NOT EXISTS turns_ad AFTER DELETE ON turns BEGIN
              INSERT INTO turns_fts(turns_fts, rowid, content, thread_id)
                VALUES ('delete', old.id, old.content, old.thread_id);
            END;
            """
        )
        self._conn.commit()

    def log(
        self,
        *,
        role: str,
        content: str,
        thread_id: str = "default",
        meta: dict | None = None,
    ) -> int:
        c = self._conn.cursor()
        c.execute(
            "INSERT INTO turns(ts, thread_id, role, content, meta) VALUES (?, ?, ?, ?, ?)",
            (time.time(), thread_id, role, content, json.dumps(meta) if meta else None),
        )
        self._conn.commit()
        return c.lastrowid or 0

    def recent(self, n: int = 20, thread_id: str | None = None) -> list[dict[str, Any]]:
        c = self._conn.cursor()
        if thread_id:
            rows = c.execute(
                "SELECT id, ts, thread_id, role, content, meta FROM turns WHERE thread_id=? ORDER BY ts DESC LIMIT ?",
                (thread_id, n),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT id, ts, thread_id, role, content, meta FROM turns ORDER BY ts DESC LIMIT ?",
                (n,),
            ).fetchall()
        return [dict(r) for r in rows]

    def search(self, query: str, n: int = 10) -> list[dict[str, Any]]:
        """Keyword search via FTS5. Returns recency-mixed results."""
        c = self._conn.cursor()
        try:
            rows = c.execute(
                """
                SELECT t.id, t.ts, t.thread_id, t.role, t.content
                FROM turns_fts f
                JOIN turns t ON t.id = f.rowid
                WHERE turns_fts MATCH ?
                ORDER BY t.ts DESC
                LIMIT ?
                """,
                (query, n),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            # FTS5 syntax errors on weird queries; fall back to LIKE
            like = f"%{query}%"
            rows = c.execute(
                "SELECT id, ts, thread_id, role, content FROM turns WHERE content LIKE ? ORDER BY ts DESC LIMIT ?",
                (like, n),
            ).fetchall()
            return [dict(r) for r in rows]

    def count(self) -> int:
        (n,) = self._conn.execute("SELECT COUNT(*) FROM turns").fetchone()
        return int(n)

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass
