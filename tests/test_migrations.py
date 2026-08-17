from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from src.models.entities import DecompositionProposal, Task, TimeEntry
from src.repositories.database import Database
from src.repositories.dependency_repository import DependencyRepository
from src.repositories.migrations import (
    BASELINE_COLUMNS,
    MIGRATIONS,
    Migration,
    MigrationError,
    migrate,
)
from src.repositories.planning_repository import PlanningRepository
from src.repositories.task_repository import TaskRepository
from src.repositories.time_entry_repository import TimeEntryRepository


ORIGINAL_TABLES = ("tasks", "journal_entries", "memories", "audit_history")


def _snapshot(conn: sqlite3.Connection) -> dict[str, list[tuple]]:
    return {
        table: [
            tuple(row)
            for row in conn.execute(
                f'SELECT {", ".join(BASELINE_COLUMNS[table])} FROM "{table}"'
            )
        ]
        for table in ORIGINAL_TABLES
    }


def _create_v08_database(path: Path) -> dict[str, list[tuple]]:
    fixture = Path(__file__).parent / "fixtures" / "v08_schema.sql"
    with sqlite3.connect(path) as conn:
        conn.executescript(fixture.read_text(encoding="utf-8"))
        return _snapshot(conn)


def test_fresh_database_receives_all_migrations_and_foreign_keys(db):
    with db.connect() as conn:
        versions = [
            row[0]
            for row in conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    assert versions == [1, 2]
    assert {
        "task_dependencies",
        "time_entries",
        "decomposition_proposals",
        "proposal_task_links",
        "reporting_settings",
        "task_deletion_audit",
    } <= tables


def test_v08_upgrade_preserves_original_rows_and_values(tmp_path):
    path = tmp_path / "daybook.db"
    before = _create_v08_database(path)

    database = Database(path)

    with database.connect() as conn:
        assert _snapshot(conn) == before
        task = conn.execute("SELECT * FROM tasks WHERE id = 7").fetchone()
        assert task["estimated_hours"] is None
        assert task["task_type"] == "standard"
        assert task["provenance"] == "user_created"
        assert task["completion_criterion"] == ""
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    backup_path = tmp_path / "daybook.v0.8.backup.db"
    assert database.backup_path == backup_path
    assert backup_path.exists()
    with sqlite3.connect(backup_path) as backup:
        assert _snapshot(backup) == before


def test_migration_is_idempotent(tmp_path):
    path = tmp_path / "daybook.db"
    _create_v08_database(path)
    Database(path)

    with sqlite3.connect(path) as conn:
        before = list(conn.iterdump())

    Database(path)

    with sqlite3.connect(path) as conn:
        after = list(conn.iterdump())
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 2
    assert after == before


def test_versioned_v08_baseline_upgrades(tmp_path):
    path = tmp_path / "versioned.db"
    before = _create_v08_database(path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "INSERT INTO schema_migrations(version, name) VALUES (1, 'v0.8 baseline')"
        )

    database = Database(path)

    with database.connect() as conn:
        assert _snapshot(conn) == before
        assert [
            row[0]
            for row in conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ] == [1, 2]


def test_failed_migration_rolls_back_and_leaves_database_usable(tmp_path):
    path = tmp_path / "daybook.db"
    database = Database(path)

    def fail_after_write(conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE should_rollback(id INTEGER)")
        raise RuntimeError("injected migration failure")

    failing = Migration(3, "injected failure", fail_after_write)
    with database.connect() as conn:
        with pytest.raises(RuntimeError, match="injected migration failure"):
            migrate(conn, path, migrations=(*MIGRATIONS, failing))

    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'should_rollback'"
        ).fetchone() is None
        assert [
            row[0]
            for row in conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ] == [1, 2]


def test_unknown_unversioned_schema_fails_without_mutation(tmp_path):
    path = tmp_path / "unknown.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE unexpected(value TEXT)")

    with pytest.raises(MigrationError, match="Unrecognized database structure"):
        Database(path)

    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall() == [("unexpected",)]


def test_unapproved_partial_v09_schema_is_rejected(tmp_path):
    path = tmp_path / "partial.db"
    _create_v08_database(path)
    with sqlite3.connect(path) as conn:
        conn.execute("ALTER TABLE tasks ADD COLUMN estimated_hours REAL")

    with pytest.raises(MigrationError, match="Unrecognized database structure"):
        Database(path)

    with sqlite3.connect(path) as conn:
        assert "estimated_hours" in {
            row[1] for row in conn.execute("PRAGMA table_info(tasks)")
        }
        assert "schema_migrations" not in {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }


def test_constraints_indexes_and_foreign_key_actions(db):
    with db.connect() as conn:
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        assert {
            "uq_tasks_parent_order",
            "idx_tasks_status_due_date",
            "idx_tasks_parent_task_id",
            "idx_task_dependencies_prerequisite",
            "idx_time_entries_work_date",
            "idx_time_entries_task_work_date",
            "idx_decomposition_proposals_parent_status",
        } <= indexes

        conn.execute("INSERT INTO tasks(title) VALUES ('Parent')")
        parent_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO tasks(title, parent_task_id, subtask_order) VALUES (?, ?, ?)",
            ("Child", parent_id, 0),
        )
        child_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO time_entries(task_id, work_date, minutes) VALUES (?, ?, ?)",
            (child_id, "2026-08-05", 15),
        )
        conn.execute("DELETE FROM tasks WHERE id = ?", (parent_id,))
        assert conn.execute(
            "SELECT parent_task_id FROM tasks WHERE id = ?", (child_id,)
        ).fetchone()[0] is None

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO time_entries(task_id, work_date, minutes) VALUES (?, ?, ?)",
                (child_id, "2026-08-05", 721),
            )


def test_repository_foundations_round_trip_rows(db):
    tasks = TaskRepository(db)
    prerequisite = tasks.create(Task(None, "Prerequisite"))
    dependent = tasks.create(Task(None, "Dependent"))

    dependencies = DependencyRepository(db)
    dependencies.create(dependent.id, prerequisite.id)
    assert dependencies.list_for_task(dependent.id)[0].prerequisite_task_id == prerequisite.id

    entries = TimeEntryRepository(db)
    entry = entries.create(
        TimeEntry(None, dependent.id, date(2026, 8, 5), 30, "Foundation test")
    )
    assert entries.get(entry.id).minutes == 30

    proposals = PlanningRepository(db)
    proposal = proposals.save(
        DecompositionProposal(
            "proposal-1",
            dependent.id,
            '{"items":[]}',
            "fingerprint-1",
        )
    )
    assert proposals.get(proposal.proposal_id).payload_json == '{"items":[]}'
