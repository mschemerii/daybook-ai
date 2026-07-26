from __future__ import annotations

from datetime import date, datetime

from src.models.entities import Task
from src.repositories.database import Database


class TaskRepository:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _row_to_task(row) -> Task:
        return Task(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            priority=row["priority"],
            due_date=date.fromisoformat(row["due_date"]) if row["due_date"] else None,
            status=row["status"],
            source=row["source"],
            notes=row["notes"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def create(self, task: Task) -> Task:
        with self.db.connect() as conn:
            cur = conn.execute(
                """INSERT INTO tasks(title, description, priority, due_date, status, source, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (task.title, task.description, task.priority,
                 task.due_date.isoformat() if task.due_date else None,
                 task.status, task.source, task.notes),
            )
            task_id = cur.lastrowid
        return self.get(task_id)

    def get(self, task_id: int) -> Task:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise KeyError(f"Task {task_id} not found")
        return self._row_to_task(row)

    def list_all(self, include_completed: bool = True) -> list[Task]:
        sql = "SELECT * FROM tasks"
        params: tuple = ()
        if not include_completed:
            sql += " WHERE status != ?"
            params = ("Completed",)
        sql += " ORDER BY created_at DESC"
        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_task(r) for r in rows]

    def update(self, task_id: int, values: dict) -> Task:
        allowed = {"title", "description", "priority", "due_date", "status", "source", "notes"}
        values = {k: v for k, v in values.items() if k in allowed}
        if not values:
            return self.get(task_id)
        if "due_date" in values and isinstance(values["due_date"], date):
            values["due_date"] = values["due_date"].isoformat()
        assignments = ", ".join(f"{k} = ?" for k in values)
        params = [*values.values(), task_id]
        with self.db.connect() as conn:
            conn.execute(
                f"UPDATE tasks SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                params,
            )
        return self.get(task_id)

    def delete(self, task_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
