from __future__ import annotations

from datetime import date, timedelta

from src.repositories.database import Database
from src.repositories.demo_seed import DEMO_TASKS


def test_demo_seed_populates_only_opted_in_fresh_database(tmp_path):
    unseeded = Database(tmp_path / "unseeded.db")
    with unseeded.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0

    seeded = Database(tmp_path / "seeded.db", seed_demo=True)
    with seeded.connect() as conn:
        rows = conn.execute(
            """
            SELECT
                title,
                priority,
                due_date,
                estimated_hours,
                task_type,
                source,
                provenance
            FROM tasks
            ORDER BY id
            """
        ).fetchall()

    assert [row["title"] for row in rows] == [
        task["title"] for task in DEMO_TASKS
    ]
    assert [row["task_type"] for row in rows] == ["standard"] * len(DEMO_TASKS)
    assert [row["source"] for row in rows] == [
        "Included sample data"
    ] * len(DEMO_TASKS)
    assert [row["provenance"] for row in rows] == [
        "user_created"
    ] * len(DEMO_TASKS)
    assert [row["due_date"] for row in rows] == [
        (date.today() + timedelta(days=task["due_offset_days"])).isoformat()
        for task in DEMO_TASKS
    ]


def test_demo_seed_is_first_launch_only(tmp_path):
    path = tmp_path / "seeded.db"
    database = Database(path, seed_demo=True)

    with database.connect() as conn:
        original_ids = [
            row[0] for row in conn.execute("SELECT id FROM tasks ORDER BY id")
        ]
        conn.execute(
            "UPDATE tasks SET title = ? WHERE id = ?",
            ("User changed this demo task", original_ids[0]),
        )

    Database(path, seed_demo=True)

    with database.connect() as conn:
        rows = conn.execute(
            "SELECT id, title FROM tasks ORDER BY id"
        ).fetchall()

    assert [row["id"] for row in rows] == original_ids
    assert rows[0]["title"] == "User changed this demo task"
    assert len(rows) == len(DEMO_TASKS)
