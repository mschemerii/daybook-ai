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
    def _task_row(conn, task_id: int):
        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Task {task_id} not found")
        return row

    @staticmethod
    def _next_subtask_order(conn, parent_task_id: int) -> int:
        row = conn.execute(
            """
            SELECT COALESCE(MAX(subtask_order), -1) + 1
            FROM tasks
            WHERE parent_task_id = ?
            """,
            (parent_task_id,),
        ).fetchone()
        return int(row[0])

    @staticmethod
    def _insert(conn, task: Task, *, parent_task_id=None, subtask_order=None) -> int:
        cur = conn.execute(
            """INSERT INTO tasks(
                   title, description, priority, due_date, status, source, notes,
                   estimated_hours, task_type, parent_task_id, subtask_order,
                   provenance, completion_criterion
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task.title,
                task.description,
                task.priority,
                task.due_date.isoformat() if task.due_date else None,
                task.status,
                task.source,
                task.notes,
                task.estimated_hours,
                "standard",
                parent_task_id,
                subtask_order,
                task.provenance,
                task.completion_criterion,
            ),
        )
        return int(cur.lastrowid)

    @staticmethod
    def _refresh_task_type(conn, task_id: int) -> None:
        has_children = conn.execute(
            "SELECT 1 FROM tasks WHERE parent_task_id = ? LIMIT 1",
            (task_id,),
        ).fetchone()
        conn.execute(
            "UPDATE tasks SET task_type = ? WHERE id = ?",
            ("epic" if has_children else "standard", task_id),
        )

    @staticmethod
    def _would_create_hierarchy_cycle(
        conn,
        task_id: int,
        new_parent_task_id: int,
    ) -> bool:
        if task_id == new_parent_task_id:
            return True
        return conn.execute(
            """
            WITH RECURSIVE descendants(id) AS (
                SELECT id FROM tasks WHERE parent_task_id = ?
                UNION ALL
                SELECT tasks.id
                FROM tasks
                JOIN descendants ON tasks.parent_task_id = descendants.id
            )
            SELECT 1 FROM descendants WHERE id = ? LIMIT 1
            """,
            (task_id, new_parent_task_id),
        ).fetchone() is not None

    @classmethod
    def _reopen_completed_ancestors(cls, conn, task_id: int) -> None:
        parent_id = cls._task_row(conn, task_id)["parent_task_id"]
        while parent_id is not None:
            parent = cls._task_row(conn, parent_id)
            if parent["status"] == "Completed":
                conn.execute(
                    "UPDATE tasks SET status = 'Open', updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = ?",
                    (parent_id,),
                )
            parent_id = parent["parent_task_id"]

    @staticmethod
    def _assert_epic_can_complete(conn, task_id: int) -> None:
        task = conn.execute(
            "SELECT task_type FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        if task is None:
            raise KeyError(f"Task {task_id} not found")
        if task["task_type"] != "epic":
            return
        incomplete = conn.execute(
            """
            SELECT title
            FROM tasks
            WHERE parent_task_id = ? AND status != 'Completed'
            ORDER BY subtask_order, id
            """,
            (task_id,),
        ).fetchall()
        if incomplete:
            names = ", ".join(row["title"] for row in incomplete)
            raise ValueError(
                "Complete every subtask before closing this epic. "
                f"Incomplete: {names}"
            )

    def create(self, task: Task) -> Task:
        if task.task_type != "standard":
            raise ValueError("A task becomes an epic only after it has a subtask")
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            parent_id = task.parent_task_id
            order = task.subtask_order
            if parent_id is not None:
                parent = self._task_row(conn, parent_id)
                if order is None:
                    order = self._next_subtask_order(conn, parent_id)
                if parent["status"] == "Completed" and task.status != "Completed":
                    conn.execute(
                        "UPDATE tasks SET status = 'Open', updated_at = CURRENT_TIMESTAMP "
                        "WHERE id = ?",
                        (parent_id,),
                    )
                    self._reopen_completed_ancestors(conn, parent_id)
            elif order is not None:
                raise ValueError("A root task cannot have a subtask order")

            task_id = self._insert(
                conn,
                task,
                parent_task_id=parent_id,
                subtask_order=order,
            )
            if parent_id is not None:
                self._refresh_task_type(conn, parent_id)
        return self.get(task_id)

    def add_subtask(self, parent_task_id: int, task: Task) -> Task:
        task.parent_task_id = parent_task_id
        task.subtask_order = None
        task.task_type = "standard"
        return self.create(task)

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

    def list_roots(self, include_completed: bool = True) -> list[Task]:
        sql = "SELECT * FROM tasks WHERE parent_task_id IS NULL"
        params: tuple = ()
        if not include_completed:
            sql += " AND status != ?"
            params = ("Completed",)
        sql += " ORDER BY created_at DESC, id DESC"
        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_task(row) for row in rows]

    def list_subtasks(self, parent_task_id: int) -> list[Task]:
        with self.db.connect() as conn:
            self._task_row(conn, parent_task_id)
            rows = conn.execute(
                """
                SELECT * FROM tasks
                WHERE parent_task_id = ?
                ORDER BY subtask_order, id
                """,
                (parent_task_id,),
            ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def descendant_ids(self, task_id: int) -> set[int]:
        with self.db.connect() as conn:
            self._task_row(conn, task_id)
            rows = conn.execute(
                """
                WITH RECURSIVE descendants(id) AS (
                    SELECT id FROM tasks WHERE parent_task_id = ?
                    UNION ALL
                    SELECT tasks.id
                    FROM tasks
                    JOIN descendants ON tasks.parent_task_id = descendants.id
                )
                SELECT id FROM descendants
                """,
                (task_id,),
            ).fetchall()
        return {int(row["id"]) for row in rows}

    def subtask_estimated_hours(self, parent_task_id: int) -> float:
        with self.db.connect() as conn:
            self._task_row(conn, parent_task_id)
            total = conn.execute(
                """
                SELECT COALESCE(SUM(estimated_hours), 0)
                FROM tasks
                WHERE parent_task_id = ?
                """,
                (parent_task_id,),
            ).fetchone()[0]
        return float(total)

    def update(self, task_id: int, values: dict) -> Task:
        allowed = {
            "title", "description", "priority", "due_date", "status", "source", "notes",
            "estimated_hours", "provenance", "completion_criterion",
        }
        values = {k: v for k, v in values.items() if k in allowed}
        if not values:
            return self.get(task_id)
        if "due_date" in values and isinstance(values["due_date"], date):
            values["due_date"] = values["due_date"].isoformat()
        assignments = ", ".join(f"{k} = ?" for k in values)
        params = [*values.values(), task_id]
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = self._task_row(conn, task_id)
            if values.get("status") == "Completed":
                self._assert_epic_can_complete(conn, task_id)
            conn.execute(
                f"UPDATE tasks SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                params,
            )
            if (
                current["status"] == "Completed"
                and values.get("status") not in (None, "Completed")
            ):
                self._reopen_completed_ancestors(conn, task_id)
        return self.get(task_id)

    def detach_subtask(self, task_id: int) -> Task:
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            task = self._task_row(conn, task_id)
            old_parent_id = task["parent_task_id"]
            if old_parent_id is None:
                raise ValueError("Task is not a subtask")
            conn.execute(
                """
                UPDATE tasks
                SET parent_task_id = NULL, subtask_order = NULL
                WHERE id = ?
                """,
                (task_id,),
            )
            self._compact_subtask_order(conn, old_parent_id)
            self._refresh_task_type(conn, old_parent_id)
        return self.get(task_id)

    @staticmethod
    def _compact_subtask_order(conn, parent_task_id: int) -> None:
        rows = conn.execute(
            """
            SELECT id FROM tasks
            WHERE parent_task_id = ?
            ORDER BY subtask_order, id
            """,
            (parent_task_id,),
        ).fetchall()
        temporary_start = conn.execute(
            "SELECT COALESCE(MAX(subtask_order), -1) + 1 FROM tasks "
            "WHERE parent_task_id = ?",
            (parent_task_id,),
        ).fetchone()[0]
        for temporary_order, row in enumerate(rows, start=temporary_start):
            conn.execute(
                "UPDATE tasks SET subtask_order = ? WHERE id = ?",
                (temporary_order, row["id"]),
            )
        for final_order, row in enumerate(rows):
            conn.execute(
                "UPDATE tasks SET subtask_order = ? WHERE id = ?",
                (final_order, row["id"]),
            )

    def reassign_subtask(self, task_id: int, new_parent_task_id: int) -> Task:
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            task = self._task_row(conn, task_id)
            new_parent = self._task_row(conn, new_parent_task_id)
            old_parent_id = task["parent_task_id"]
            if old_parent_id == new_parent_task_id:
                return self._row_to_task(task)
            if self._would_create_hierarchy_cycle(conn, task_id, new_parent_task_id):
                raise ValueError("A task cannot be moved beneath itself or its descendants")

            new_order = self._next_subtask_order(conn, new_parent_task_id)
            conn.execute(
                """
                UPDATE tasks
                SET parent_task_id = ?, subtask_order = ?
                WHERE id = ?
                """,
                (new_parent_task_id, new_order, task_id),
            )
            if old_parent_id is not None:
                self._compact_subtask_order(conn, old_parent_id)
                self._refresh_task_type(conn, old_parent_id)
            self._refresh_task_type(conn, new_parent_task_id)
            if new_parent["status"] == "Completed" and task["status"] != "Completed":
                conn.execute(
                    "UPDATE tasks SET status = 'Open', updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = ?",
                    (new_parent_task_id,),
                )
                self._reopen_completed_ancestors(conn, new_parent_task_id)
        return self.get(task_id)

    def reorder_subtasks(self, parent_task_id: int, ordered_task_ids: list[int]) -> list[Task]:
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            parent = self._task_row(conn, parent_task_id)
            current_ids = [
                row["id"]
                for row in conn.execute(
                    """
                    SELECT id FROM tasks
                    WHERE parent_task_id = ?
                    ORDER BY subtask_order, id
                    """,
                    (parent_task_id,),
                ).fetchall()
            ]
            if len(ordered_task_ids) != len(set(ordered_task_ids)):
                raise ValueError("Subtask order cannot contain duplicate task IDs")
            if set(current_ids) != set(ordered_task_ids):
                raise ValueError("Subtask order must contain every current subtask exactly once")
            temporary_start = conn.execute(
                "SELECT COALESCE(MAX(subtask_order), -1) + 1 FROM tasks "
                "WHERE parent_task_id = ?",
                (parent_task_id,),
            ).fetchone()[0]
            for temporary_order, child_id in enumerate(
                ordered_task_ids,
                start=temporary_start,
            ):
                conn.execute(
                    "UPDATE tasks SET subtask_order = ? WHERE id = ?",
                    (temporary_order, child_id),
                )
            for final_order, child_id in enumerate(ordered_task_ids):
                conn.execute(
                    "UPDATE tasks SET subtask_order = ? WHERE id = ?",
                    (final_order, child_id),
                )
            if parent["task_type"] != "epic" and ordered_task_ids:
                self._refresh_task_type(conn, parent_task_id)
        return self.list_subtasks(parent_task_id)

    def delete(self, task_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            task = self._task_row(conn, task_id)
            parent_id = task["parent_task_id"]
            if task["task_type"] == "epic":
                raise ValueError(
                    "Epic deletion requires the governed deletion preview."
                )
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            if parent_id is not None:
                self._compact_subtask_order(conn, parent_id)
                self._refresh_task_type(conn, parent_id)

    def deletion_details(self, task_id: int) -> tuple[Task, list[Task], set[int]]:
        task = self.get(task_id)
        descendants = [
            item
            for item in self.list_all(include_completed=True)
            if item.id in self.descendant_ids(task_id)
        ]
        with self.db.connect() as conn:
            timed_ids = {
                int(row["task_id"])
                for row in conn.execute(
                    "SELECT DISTINCT task_id FROM time_entries"
                ).fetchall()
            }
        return task, descendants, timed_ids

    def governed_delete(self, task_id: int) -> None:
        """Delete one task while preserving timed epic descendants atomically."""
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            task = self._task_row(conn, task_id)
            parent_id = task["parent_task_id"]
            descendant_rows = conn.execute(
                """
                WITH RECURSIVE descendants(id) AS (
                    SELECT id FROM tasks WHERE parent_task_id = ?
                    UNION ALL
                    SELECT tasks.id FROM tasks
                    JOIN descendants ON tasks.parent_task_id = descendants.id
                )
                SELECT tasks.* FROM tasks JOIN descendants USING(id)
                """,
                (task_id,),
            ).fetchall()
            timed_ids = {
                int(row["task_id"])
                for row in conn.execute(
                    "SELECT DISTINCT task_id FROM time_entries"
                ).fetchall()
            }
            preserved_ids = {
                int(row["id"])
                for row in descendant_rows
                if int(row["id"]) in timed_ids
            }
            for preserved_id in preserved_ids:
                conn.execute(
                    """
                    UPDATE tasks
                    SET parent_task_id = NULL, subtask_order = NULL,
                        task_type = 'standard'
                    WHERE id = ?
                    """,
                    (preserved_id,),
                )
            deleted_ids = [
                int(row["id"])
                for row in descendant_rows
                if int(row["id"]) not in preserved_ids
            ]
            action = (
                "delete_epic_preserve_timed_subtasks"
                if descendant_rows
                else "delete_task_with_time"
                if task_id in timed_ids
                else "delete_task"
            )
            conn.execute(
                "INSERT INTO task_deletion_audit(deleted_task_id, deletion_action) "
                "VALUES (?, ?)",
                (task_id, action),
            )
            for deleted_id in deleted_ids:
                conn.execute(
                    "INSERT INTO task_deletion_audit(deleted_task_id, deletion_action) "
                    "VALUES (?, 'delete_with_epic')",
                    (deleted_id,),
                )
            if deleted_ids:
                placeholders = ", ".join("?" for _ in deleted_ids)
                conn.execute(
                    f"DELETE FROM tasks WHERE id IN ({placeholders})",
                    tuple(deleted_ids),
                )
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            if parent_id is not None:
                self._compact_subtask_order(conn, parent_id)
                self._refresh_task_type(conn, parent_id)

    def deletion_audit(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM task_deletion_audit ORDER BY id"
            ).fetchall()
        return [dict(row) for row in rows]
