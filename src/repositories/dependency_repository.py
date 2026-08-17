from __future__ import annotations

from datetime import datetime

from src.models.entities import Task, TaskDependency
from src.repositories.database import Database


class DependencyRepository:
    """Persist dependency edges and atomic dependency lifecycle changes."""

    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _row_to_task(row) -> Task:
        from src.repositories.task_repository import TaskRepository

        return TaskRepository._row_to_task(row)

    def create(self, dependent_task_id: int, prerequisite_task_id: int) -> TaskDependency:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO task_dependencies(dependent_task_id, prerequisite_task_id)
                VALUES (?, ?)
                """,
                (dependent_task_id, prerequisite_task_id),
            )
        return TaskDependency(dependent_task_id, prerequisite_task_id)

    def exists(self, dependent_task_id: int, prerequisite_task_id: int) -> bool:
        with self.db.connect() as conn:
            return conn.execute(
                """
                SELECT 1 FROM task_dependencies
                WHERE dependent_task_id = ? AND prerequisite_task_id = ?
                """,
                (dependent_task_id, prerequisite_task_id),
            ).fetchone() is not None

    def list_for_task(self, dependent_task_id: int) -> list[TaskDependency]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT dependent_task_id, prerequisite_task_id, created_at
                FROM task_dependencies
                WHERE dependent_task_id = ?
                ORDER BY prerequisite_task_id
                """,
                (dependent_task_id,),
            ).fetchall()
        return [
            TaskDependency(
                row["dependent_task_id"],
                row["prerequisite_task_id"],
                datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def list_dependents(self, prerequisite_task_id: int) -> list[TaskDependency]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT dependent_task_id, prerequisite_task_id, created_at
                FROM task_dependencies
                WHERE prerequisite_task_id = ?
                ORDER BY dependent_task_id
                """,
                (prerequisite_task_id,),
            ).fetchall()
        return [
            TaskDependency(
                row["dependent_task_id"],
                row["prerequisite_task_id"],
                datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def dependency_pairs(self) -> list[tuple[int, int]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT dependent_task_id, prerequisite_task_id
                FROM task_dependencies
                ORDER BY dependent_task_id, prerequisite_task_id
                """
            ).fetchall()
        return [
            (int(row["dependent_task_id"]), int(row["prerequisite_task_id"]))
            for row in rows
        ]

    def incomplete_prerequisites(self, dependent_task_id: int) -> list[Task]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT tasks.*
                FROM task_dependencies
                JOIN tasks ON tasks.id = task_dependencies.prerequisite_task_id
                WHERE task_dependencies.dependent_task_id = ?
                  AND tasks.status != 'Completed'
                ORDER BY tasks.title COLLATE NOCASE, tasks.id
                """,
                (dependent_task_id,),
            ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def prerequisite_tasks(self, dependent_task_id: int) -> list[Task]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT tasks.*
                FROM task_dependencies
                JOIN tasks ON tasks.id = task_dependencies.prerequisite_task_id
                WHERE task_dependencies.dependent_task_id = ?
                ORDER BY tasks.title COLLATE NOCASE, tasks.id
                """,
                (dependent_task_id,),
            ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def dependent_tasks(self, prerequisite_task_id: int) -> list[Task]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT tasks.*
                FROM task_dependencies
                JOIN tasks ON tasks.id = task_dependencies.dependent_task_id
                WHERE task_dependencies.prerequisite_task_id = ?
                ORDER BY tasks.title COLLATE NOCASE, tasks.id
                """,
                (prerequisite_task_id,),
            ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def affected_dependents(self, prerequisite_task_id: int) -> list[Task]:
        """Return direct and transitive dependents in nearest-first order."""
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                WITH RECURSIVE affected(id, depth) AS (
                    SELECT dependent_task_id, 1
                    FROM task_dependencies
                    WHERE prerequisite_task_id = ?
                    UNION
                    SELECT dependency.dependent_task_id, affected.depth + 1
                    FROM task_dependencies AS dependency
                    JOIN affected
                      ON dependency.prerequisite_task_id = affected.id
                )
                SELECT tasks.*, MIN(affected.depth) AS dependency_depth
                FROM affected
                JOIN tasks ON tasks.id = affected.id
                GROUP BY tasks.id
                ORDER BY dependency_depth, tasks.title COLLATE NOCASE, tasks.id
                """,
                (prerequisite_task_id,),
            ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def reopen_cascade(self, prerequisite_task_id: int) -> Task:
        """Atomically reopen a prerequisite, invalid dependents, and ancestors."""
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            root = conn.execute(
                "SELECT * FROM tasks WHERE id = ?",
                (prerequisite_task_id,),
            ).fetchone()
            if root is None:
                raise KeyError(f"Task {prerequisite_task_id} not found")

            affected_rows = conn.execute(
                """
                WITH RECURSIVE affected(id) AS (
                    SELECT dependent_task_id
                    FROM task_dependencies
                    WHERE prerequisite_task_id = ?
                    UNION
                    SELECT dependency.dependent_task_id
                    FROM task_dependencies AS dependency
                    JOIN affected
                      ON dependency.prerequisite_task_id = affected.id
                )
                SELECT id FROM affected
                """,
                (prerequisite_task_id,),
            ).fetchall()
            affected_ids = {int(row["id"]) for row in affected_rows}
            cascade_ids = {prerequisite_task_id, *affected_ids}

            placeholders = ", ".join("?" for _ in cascade_ids)
            conn.execute(
                f"""
                UPDATE tasks
                SET status = 'Open', updated_at = CURRENT_TIMESTAMP
                WHERE id IN ({placeholders}) AND status = 'Completed'
                """,
                tuple(cascade_ids),
            )

            ancestor_rows = conn.execute(
                f"""
                WITH RECURSIVE ancestors(id) AS (
                    SELECT parent_task_id
                    FROM tasks
                    WHERE id IN ({placeholders}) AND parent_task_id IS NOT NULL
                    UNION
                    SELECT tasks.parent_task_id
                    FROM tasks
                    JOIN ancestors ON tasks.id = ancestors.id
                    WHERE tasks.parent_task_id IS NOT NULL
                )
                SELECT id FROM ancestors
                """,
                tuple(cascade_ids),
            ).fetchall()
            ancestor_ids = {int(row["id"]) for row in ancestor_rows}
            if ancestor_ids:
                ancestor_placeholders = ", ".join("?" for _ in ancestor_ids)
                conn.execute(
                    f"""
                    UPDATE tasks
                    SET status = 'Open', updated_at = CURRENT_TIMESTAMP
                    WHERE id IN ({ancestor_placeholders})
                      AND status = 'Completed'
                    """,
                    tuple(ancestor_ids),
                )

        from src.repositories.task_repository import TaskRepository

        return TaskRepository(self.db).get(prerequisite_task_id)

    def convert_pair_to_epic(
        self,
        dependent_task_id: int,
        prerequisite_task_id: int,
        epic_title: str,
    ) -> Task:
        """Atomically create an epic and place prerequisite before dependent."""
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            dependent = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (dependent_task_id,)
            ).fetchone()
            prerequisite = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (prerequisite_task_id,)
            ).fetchone()
            if dependent is None or prerequisite is None:
                raise KeyError("A dependency task no longer exists")
            if not conn.execute(
                """
                SELECT 1 FROM task_dependencies
                WHERE dependent_task_id = ? AND prerequisite_task_id = ?
                """,
                (dependent_task_id, prerequisite_task_id),
            ).fetchone():
                raise ValueError("The dependency no longer exists")
            if any(
                row["task_type"] != "standard" or row["parent_task_id"] is not None
                for row in (dependent, prerequisite)
            ):
                raise ValueError("Both tasks must still be standalone regular tasks")

            cursor = conn.execute(
                """
                INSERT INTO tasks(title, source, task_type)
                VALUES (?, 'User', 'epic')
                """,
                (epic_title,),
            )
            epic_id = int(cursor.lastrowid)
            conn.execute(
                """
                UPDATE tasks SET parent_task_id = ?, subtask_order = 0
                WHERE id = ?
                """,
                (epic_id, prerequisite_task_id),
            )
            conn.execute(
                """
                UPDATE tasks SET parent_task_id = ?, subtask_order = 1
                WHERE id = ?
                """,
                (epic_id, dependent_task_id),
            )

        from src.repositories.task_repository import TaskRepository

        return TaskRepository(self.db).get(epic_id)

    def append_dependent_to_epic(
        self,
        dependent_task_id: int,
        epic_task_id: int,
    ) -> Task:
        """Atomically move a dependent under an epic and remove parent dependency."""
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            dependent = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (dependent_task_id,)
            ).fetchone()
            epic = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (epic_task_id,)
            ).fetchone()
            if dependent is None or epic is None:
                raise KeyError("A dependency task no longer exists")
            if dependent["task_type"] != "standard" or dependent["parent_task_id"] is not None:
                raise ValueError("The dependent must still be a standalone regular task")
            if epic["task_type"] != "epic":
                raise ValueError("The prerequisite must still be an epic")
            if not conn.execute(
                """
                SELECT 1 FROM task_dependencies
                WHERE dependent_task_id = ? AND prerequisite_task_id = ?
                """,
                (dependent_task_id, epic_task_id),
            ).fetchone():
                raise ValueError("The dependency no longer exists")

            next_order = int(
                conn.execute(
                    """
                    SELECT COALESCE(MAX(subtask_order), -1) + 1
                    FROM tasks WHERE parent_task_id = ?
                    """,
                    (epic_task_id,),
                ).fetchone()[0]
            )
            conn.execute(
                """
                DELETE FROM task_dependencies
                WHERE dependent_task_id = ? AND prerequisite_task_id = ?
                """,
                (dependent_task_id, epic_task_id),
            )
            conn.execute(
                """
                UPDATE tasks SET parent_task_id = ?, subtask_order = ?
                WHERE id = ?
                """,
                (epic_task_id, next_order, dependent_task_id),
            )
            if epic["status"] == "Completed" and dependent["status"] != "Completed":
                conn.execute(
                    """
                    UPDATE tasks SET status = 'Open', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (epic_task_id,),
                )
                ancestor_id = epic["parent_task_id"]
                while ancestor_id is not None:
                    ancestor = conn.execute(
                        "SELECT parent_task_id, status FROM tasks WHERE id = ?",
                        (ancestor_id,),
                    ).fetchone()
                    if ancestor["status"] == "Completed":
                        conn.execute(
                            """
                            UPDATE tasks
                            SET status = 'Open', updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                            """,
                            (ancestor_id,),
                        )
                    ancestor_id = ancestor["parent_task_id"]

        from src.repositories.task_repository import TaskRepository

        return TaskRepository(self.db).get(dependent_task_id)

    def delete(self, dependent_task_id: int, prerequisite_task_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                DELETE FROM task_dependencies
                WHERE dependent_task_id = ? AND prerequisite_task_id = ?
                """,
                (dependent_task_id, prerequisite_task_id),
            )
