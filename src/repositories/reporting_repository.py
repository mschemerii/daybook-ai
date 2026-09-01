from __future__ import annotations

from datetime import date, datetime

from src.models.entities import Task, TimeEntry
from src.models.reporting import ReportingSnapshot
from src.repositories.database import Database


class ReportingRepository:
    """Read-only reporting snapshot access over authoritative Daybook tables."""

    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _task_from_row(row) -> Task:
        return Task(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            priority=row["priority"],
            due_date=date.fromisoformat(row["due_date"]) if row["due_date"] else None,
            status=row["status"],
            source=row["source"],
            notes=row["notes"],
            estimated_hours=row["estimated_hours"],
            task_type=row["task_type"],
            parent_task_id=row["parent_task_id"],
            subtask_order=row["subtask_order"],
            provenance=row["provenance"],
            completion_criterion=row["completion_criterion"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _entry_from_row(row) -> TimeEntry:
        return TimeEntry(
            id=row["id"],
            task_id=row["task_id"],
            work_date=date.fromisoformat(row["work_date"]),
            minutes=row["minutes"],
            note=row["note"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def load_snapshot(self, start_date: date, end_date: date) -> ReportingSnapshot:
        if start_date > end_date:
            raise ValueError("Report range start date must be on or before end date.")
        with self.db.connect() as conn:
            task_rows = conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
            entry_rows = conn.execute(
                "SELECT * FROM time_entries ORDER BY id"
            ).fetchall()
        entries = tuple(self._entry_from_row(row) for row in entry_rows)
        return ReportingSnapshot(
            tuple(self._task_from_row(row) for row in task_rows),
            tuple(
                entry
                for entry in entries
                if start_date <= entry.work_date <= end_date
            ),
        )
