from __future__ import annotations

from datetime import date, datetime

from src.models.entities import TimeEntry
from src.repositories.database import Database


class TimeEntryRepository:
    """Persistence only; time-entry policy belongs to the Phase 5 service."""

    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _from_row(row) -> TimeEntry:
        return TimeEntry(
            id=row["id"],
            task_id=row["task_id"],
            work_date=date.fromisoformat(row["work_date"]),
            minutes=row["minutes"],
            note=row["note"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def create(self, entry: TimeEntry) -> TimeEntry:
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO time_entries(task_id, work_date, minutes, note)
                VALUES (?, ?, ?, ?)
                """,
                (entry.task_id, entry.work_date.isoformat(), entry.minutes, entry.note),
            )
            entry_id = cursor.lastrowid
        return self.get(entry_id)

    def get(self, entry_id: int) -> TimeEntry:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM time_entries WHERE id = ?", (entry_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Time entry {entry_id} not found")
        return self._from_row(row)

    def list_for_task(self, task_id: int) -> list[TimeEntry]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM time_entries
                WHERE task_id = ?
                ORDER BY work_date, id
                """,
                (task_id,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def update(self, entry_id: int, entry: TimeEntry) -> TimeEntry:
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE time_entries
                SET work_date = ?, minutes = ?, note = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    entry.work_date.isoformat(),
                    entry.minutes,
                    entry.note,
                    entry_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Time entry {entry_id} not found")
        return self.get(entry_id)

    def delete(self, entry_id: int) -> None:
        with self.db.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM time_entries WHERE id = ?",
                (entry_id,),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Time entry {entry_id} not found")

    def minutes_for_task(self, task_id: int) -> int:
        with self.db.connect() as conn:
            total = conn.execute(
                "SELECT COALESCE(SUM(minutes), 0) FROM time_entries WHERE task_id = ?",
                (task_id,),
            ).fetchone()[0]
        return int(total)

    def minutes_for_tasks(self, task_ids: set[int]) -> int:
        if not task_ids:
            return 0
        placeholders = ", ".join("?" for _ in task_ids)
        with self.db.connect() as conn:
            total = conn.execute(
                f"SELECT COALESCE(SUM(minutes), 0) FROM time_entries "
                f"WHERE task_id IN ({placeholders})",
                tuple(sorted(task_ids)),
            ).fetchone()[0]
        return int(total)

    def minutes_for_date(self, work_date: date, *, exclude_entry_id: int | None = None) -> int:
        sql = "SELECT COALESCE(SUM(minutes), 0) FROM time_entries WHERE work_date = ?"
        params: list[object] = [work_date.isoformat()]
        if exclude_entry_id is not None:
            sql += " AND id != ?"
            params.append(exclude_entry_id)
        with self.db.connect() as conn:
            total = conn.execute(sql, params).fetchone()[0]
        return int(total)
