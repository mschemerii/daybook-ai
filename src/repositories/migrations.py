from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path


BASELINE_TABLES = {
    "tasks",
    "journal_entries",
    "memories",
    "audit_history",
}

BASELINE_COLUMNS = {
    "tasks": (
        "id",
        "title",
        "description",
        "priority",
        "due_date",
        "status",
        "source",
        "notes",
        "created_at",
        "updated_at",
    ),
    "journal_entries": (
        "entry_date",
        "completed_today",
        "in_progress",
        "blocked_waiting",
        "reflections",
        "plan_tomorrow",
        "created_at",
        "updated_at",
    ),
    "memories": ("id", "content", "created_at", "updated_at"),
    "audit_history": (
        "id",
        "created_at",
        "user_request",
        "records_consulted",
        "recommendation",
        "approved_action",
    ),
}

V09_PHASE2_TABLES = BASELINE_TABLES | {
    "schema_migrations",
    "task_dependencies",
    "time_entries",
    "decomposition_proposals",
    "proposal_task_links",
    "reporting_settings",
    "task_deletion_audit",
}

V09_TABLES = V09_PHASE2_TABLES | {
    "task_clarification_answers",
}

V09_TASK_COLUMNS = BASELINE_COLUMNS["tasks"] + (
    "estimated_hours",
    "task_type",
    "parent_task_id",
    "subtask_order",
    "provenance",
    "completion_criterion",
)


class MigrationError(RuntimeError):
    """Raised when a database cannot be upgraded safely."""


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]


BASELINE_STATEMENTS = (
    """
    CREATE TABLE tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        priority TEXT NOT NULL DEFAULT 'Medium',
        due_date TEXT,
        status TEXT NOT NULL DEFAULT 'Open',
        source TEXT NOT NULL DEFAULT 'User',
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE journal_entries (
        entry_date TEXT PRIMARY KEY,
        completed_today TEXT NOT NULL DEFAULT '',
        in_progress TEXT NOT NULL DEFAULT '',
        blocked_waiting TEXT NOT NULL DEFAULT '',
        reflections TEXT NOT NULL DEFAULT '',
        plan_tomorrow TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE audit_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        user_request TEXT NOT NULL,
        records_consulted TEXT NOT NULL,
        recommendation TEXT NOT NULL,
        approved_action INTEGER
    )
    """,
)


V09_STATEMENTS = (
    """
    ALTER TABLE tasks ADD COLUMN estimated_hours REAL
        CHECK (
            estimated_hours IS NULL OR (
                estimated_hours >= 0.25
                AND ABS((estimated_hours * 4) - ROUND(estimated_hours * 4)) < 0.000001
            )
        )
    """,
    """
    ALTER TABLE tasks ADD COLUMN task_type TEXT NOT NULL DEFAULT 'standard'
        CHECK (task_type IN ('standard', 'epic'))
    """,
    """
    ALTER TABLE tasks ADD COLUMN parent_task_id INTEGER
        REFERENCES tasks(id) ON DELETE SET NULL
    """,
    """
    ALTER TABLE tasks ADD COLUMN subtask_order INTEGER
        CHECK (subtask_order IS NULL OR subtask_order >= 0)
    """,
    """
    ALTER TABLE tasks ADD COLUMN provenance TEXT NOT NULL DEFAULT 'user_created'
        CHECK (provenance IN (
            'user_created',
            'ai_generated',
            'ai_generated_user_edited',
            'user_added_during_review'
        ))
    """,
    """
    ALTER TABLE tasks ADD COLUMN completion_criterion TEXT NOT NULL DEFAULT ''
    """,
    """
    CREATE TABLE task_dependencies (
        dependent_task_id INTEGER NOT NULL
            REFERENCES tasks(id) ON DELETE CASCADE,
        prerequisite_task_id INTEGER NOT NULL
            REFERENCES tasks(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (dependent_task_id, prerequisite_task_id),
        CHECK (dependent_task_id <> prerequisite_task_id)
    )
    """,
    """
    CREATE TABLE time_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        work_date TEXT NOT NULL,
        minutes INTEGER NOT NULL
            CHECK (TYPEOF(minutes) = 'integer' AND minutes BETWEEN 1 AND 720),
        note TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE decomposition_proposals (
        proposal_id TEXT PRIMARY KEY,
        parent_task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        payload_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft'
            CHECK (status IN ('draft', 'approved', 'rejected', 'cancelled')),
        fingerprint TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE proposal_task_links (
        proposal_id TEXT NOT NULL
            REFERENCES decomposition_proposals(proposal_id) ON DELETE CASCADE,
        item_key TEXT NOT NULL,
        task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (proposal_id, item_key),
        UNIQUE (task_id)
    )
    """,
    """
    CREATE TABLE reporting_settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        fiscal_start_month INTEGER NOT NULL DEFAULT 1
            CHECK (fiscal_start_month BETWEEN 1 AND 12),
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "INSERT INTO reporting_settings(id, fiscal_start_month) VALUES (1, 1)",
    """
    CREATE TABLE task_deletion_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        deleted_task_id INTEGER NOT NULL,
        deletion_action TEXT NOT NULL,
        deleted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE UNIQUE INDEX uq_tasks_parent_order
        ON tasks(parent_task_id, subtask_order)
        WHERE parent_task_id IS NOT NULL AND subtask_order IS NOT NULL
    """,
    "CREATE INDEX idx_tasks_status_due_date ON tasks(status, due_date)",
    "CREATE INDEX idx_tasks_parent_task_id ON tasks(parent_task_id)",
    """
    CREATE INDEX idx_task_dependencies_prerequisite
        ON task_dependencies(prerequisite_task_id)
    """,
    "CREATE INDEX idx_time_entries_work_date ON time_entries(work_date)",
    """
    CREATE INDEX idx_time_entries_task_work_date
        ON time_entries(task_id, work_date)
    """,
    """
    CREATE INDEX idx_decomposition_proposals_parent_status
        ON decomposition_proposals(parent_task_id, status)
    """,
)


def _execute_statements(conn: sqlite3.Connection, statements: Sequence[str]) -> None:
    for statement in statements:
        conn.execute(statement)


def _create_baseline(conn: sqlite3.Connection) -> None:
    _execute_statements(conn, BASELINE_STATEMENTS)


def _upgrade_to_v09(conn: sqlite3.Connection) -> None:
    _execute_statements(conn, V09_STATEMENTS)


V09_PHASE7_5_STATEMENTS = (
    """
    CREATE TABLE task_clarification_answers (
        task_id INTEGER PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
        answers_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
)


def _upgrade_to_v09_phase7_5(conn: sqlite3.Connection) -> None:
    _execute_statements(conn, V09_PHASE7_5_STATEMENTS)


MIGRATIONS = (
    Migration(1, "v0.8 baseline", _create_baseline),
    Migration(2, "v0.9 migration and repository foundation", _upgrade_to_v09),
    Migration(
        3,
        "v0.9 Phase 7.5 durable task clarification answers",
        _upgrade_to_v09_phase7_5,
    ),
)


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _columns(conn: sqlite3.Connection, table: str) -> tuple[str, ...]:
    return tuple(row[1] for row in conn.execute(f'PRAGMA table_info("{table}")'))


def _matches_baseline(conn: sqlite3.Connection) -> bool:
    if _table_names(conn) != BASELINE_TABLES:
        return False
    return all(_columns(conn, table) == columns for table, columns in BASELINE_COLUMNS.items())


def _matches_versioned_baseline(conn: sqlite3.Connection) -> bool:
    if _table_names(conn) != BASELINE_TABLES | {"schema_migrations"}:
        return False
    return all(_columns(conn, table) == columns for table, columns in BASELINE_COLUMNS.items())


def _validate_v09(
    conn: sqlite3.Connection,
    version: int | None = None,
) -> None:
    tables = _table_names(conn)
    expected_tables = V09_PHASE2_TABLES if version == 2 else V09_TABLES
    missing = expected_tables - tables
    unexpected = tables - expected_tables
    if missing or unexpected or _columns(conn, "tasks") != V09_TASK_COLUMNS:
        details = []
        if missing:
            details.append(f"missing tables: {', '.join(sorted(missing))}")
        if unexpected:
            details.append(f"unexpected tables: {', '.join(sorted(unexpected))}")
        if "tasks" in tables and _columns(conn, "tasks") != V09_TASK_COLUMNS:
            details.append("tasks columns do not match the v0.9 schema")
        raise MigrationError("Invalid v0.9 database structure (" + "; ".join(details) + ")")


def _backup_path(db_path: Path) -> Path:
    suffix = db_path.suffix or ".db"
    return db_path.with_name(f"{db_path.stem}.v0.8.backup{suffix}")


def _create_backup(conn: sqlite3.Connection, db_path: Path) -> Path:
    backup_path = _backup_path(db_path)
    if backup_path.exists():
        return backup_path
    with sqlite3.connect(backup_path) as backup:
        conn.backup(backup)
    return backup_path


def _record_migration(conn: sqlite3.Connection, migration: Migration) -> None:
    conn.execute(
        "INSERT INTO schema_migrations(version, name) VALUES (?, ?)",
        (migration.version, migration.name),
    )


def migrate(
    conn: sqlite3.Connection,
    db_path: str | Path,
    migrations: Sequence[Migration] = MIGRATIONS,
) -> Path | None:
    """Upgrade a recognized database atomically and return its backup path, if any."""
    path = Path(db_path)
    versions = [migration.version for migration in migrations]
    if versions != list(range(1, len(migrations) + 1)):
        raise MigrationError("Migration registry must contain contiguous versions starting at 1")

    tables = _table_names(conn)
    is_new = not tables
    is_unversioned_baseline = "schema_migrations" not in tables and _matches_baseline(conn)

    if not is_new and not is_unversioned_baseline and "schema_migrations" not in tables:
        raise MigrationError(
            "Unrecognized database structure. No changes were made; restore or inspect "
            "the database before retrying."
        )

    applied: set[int] = set()
    if "schema_migrations" in tables:
        applied = {
            row[0]
            for row in conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        }
        known = {migration.version for migration in migrations}
        if not applied <= known:
            raise MigrationError("Database contains an unknown migration version")
        if not applied or applied != set(range(1, max(applied) + 1)):
            raise MigrationError("Database migration history is incomplete or non-contiguous")
        if max(applied) == 1 and not _matches_versioned_baseline(conn):
            raise MigrationError("Version 1 database structure does not match the v0.8 baseline")
        if max(applied) >= 2:
            _validate_v09(conn, max(applied))

    pending = [migration for migration in migrations if migration.version not in applied]
    needs_v09 = any(migration.version >= 2 for migration in pending)
    backup_path = None
    if not is_new and needs_v09:
        backup_path = _create_backup(conn, path)

    try:
        conn.execute("BEGIN IMMEDIATE")
        if is_new:
            conn.execute(
                """
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        elif is_unversioned_baseline:
            conn.execute(
                """
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            _record_migration(conn, migrations[0])
            applied.add(migrations[0].version)

        for migration in migrations:
            if migration.version in applied:
                continue
            migration.apply(conn)
            _record_migration(conn, migration)
        _validate_v09(conn, max(versions))
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return backup_path
