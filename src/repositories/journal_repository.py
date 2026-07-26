from __future__ import annotations

from datetime import date, datetime

from src.models.entities import JournalEntry
from src.repositories.database import Database


class JournalRepository:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _row_to_entry(row) -> JournalEntry:
        return JournalEntry(
            entry_date=date.fromisoformat(row["entry_date"]),
            completed_today=row["completed_today"],
            in_progress=row["in_progress"],
            blocked_waiting=row["blocked_waiting"],
            reflections=row["reflections"],
            plan_tomorrow=row["plan_tomorrow"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def upsert(self, entry: JournalEntry) -> JournalEntry:
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO journal_entries(entry_date, completed_today, in_progress, blocked_waiting, reflections, plan_tomorrow)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(entry_date) DO UPDATE SET
                   completed_today=excluded.completed_today,
                   in_progress=excluded.in_progress,
                   blocked_waiting=excluded.blocked_waiting,
                   reflections=excluded.reflections,
                   plan_tomorrow=excluded.plan_tomorrow,
                   updated_at=CURRENT_TIMESTAMP""",
                (entry.entry_date.isoformat(), entry.completed_today, entry.in_progress,
                 entry.blocked_waiting, entry.reflections, entry.plan_tomorrow),
            )
        return self.get(entry.entry_date)

    def get(self, entry_date: date) -> JournalEntry | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM journal_entries WHERE entry_date = ?", (entry_date.isoformat(),)).fetchone()
        return self._row_to_entry(row) if row else None

    def list_recent(self, limit: int = 30) -> list[JournalEntry]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM journal_entries ORDER BY entry_date DESC LIMIT ?", (limit,)).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def search(self, query: str, limit: int = 20) -> list[JournalEntry]:
        pattern = f"%{query}%"
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT * FROM journal_entries WHERE
                completed_today LIKE ? OR in_progress LIKE ? OR blocked_waiting LIKE ? OR
                reflections LIKE ? OR plan_tomorrow LIKE ?
                ORDER BY entry_date DESC LIMIT ?""",
                (pattern, pattern, pattern, pattern, pattern, limit),
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]
