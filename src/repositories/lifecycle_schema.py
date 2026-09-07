"""Additive lifecycle history. All timestamps are UTC, never inferred from edits."""
from __future__ import annotations

import sqlite3


def install_lifecycle(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE task_lifecycle (
        id INTEGER PRIMARY KEY,
        task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        event TEXT NOT NULL,
        occurred_at TEXT,
        estimate_hours REAL,
        actual_minutes INTEGER,
        title TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE task_block_intervals (
        id INTEGER PRIMARY KEY,
        task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        blocker_key INTEGER NOT NULL,
        reason TEXT NOT NULL,
        started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ended_at TEXT,
        start_unknown INTEGER NOT NULL DEFAULT 0
    )""")
    conn.execute("CREATE UNIQUE INDEX active_task_block ON task_block_intervals(task_id, blocker_key) WHERE ended_at IS NULL")
    conn.execute("""CREATE VIEW active_task_blockers AS
        SELECT id AS task_id, 0 AS blocker_key,
               'Manually marked Blocked' || CASE WHEN notes != '' THEN ': ' || notes ELSE '' END AS reason
        FROM tasks WHERE status = 'Blocked'
        UNION ALL
        SELECT d.dependent_task_id, d.prerequisite_task_id,
               'Prerequisite: ' || p.title
        FROM task_dependencies d JOIN tasks p ON p.id=d.prerequisite_task_id
        JOIN tasks t ON t.id=d.dependent_task_id
        WHERE p.status != 'Completed' AND t.status != 'Completed'
    """)
    conn.execute("""INSERT INTO task_lifecycle(task_id,event,title)
        SELECT id, CASE WHEN status='Completed' THEN 'legacy_completed'
                       ELSE 'history_started' END, title FROM tasks""")
    conn.execute("""INSERT INTO task_block_intervals(task_id,blocker_key,reason,start_unknown)
        SELECT task_id,blocker_key,reason,1 FROM active_task_blockers""")
    # Keep intervals correct even for implicit ancestor reopen and dependency edits.
    reconcile = """
        UPDATE task_block_intervals SET ended_at=CURRENT_TIMESTAMP
        WHERE ended_at IS NULL AND NOT EXISTS (
            SELECT 1 FROM active_task_blockers a
            WHERE a.task_id=task_block_intervals.task_id
              AND a.blocker_key=task_block_intervals.blocker_key);
        INSERT INTO task_block_intervals(task_id,blocker_key,reason)
        SELECT a.task_id,a.blocker_key,a.reason FROM active_task_blockers a
        WHERE NOT EXISTS (SELECT 1 FROM task_block_intervals b
            WHERE b.task_id=a.task_id AND b.blocker_key=a.blocker_key
              AND b.ended_at IS NULL);
    """
    for table in ('tasks', 'task_dependencies'):
        for action in ('INSERT', 'UPDATE', 'DELETE'):
            conn.execute(f"CREATE TRIGGER blocks_{table}_{action.lower()} AFTER {action} ON {table} BEGIN {reconcile} END")
    conn.execute("""CREATE TRIGGER task_created_history AFTER INSERT ON tasks BEGIN
        INSERT INTO task_lifecycle(task_id,event,occurred_at,title)
        VALUES (NEW.id, CASE WHEN NEW.status='Completed' THEN 'legacy_completed' ELSE 'created' END,
                CASE WHEN NEW.status='Completed' THEN NULL ELSE CURRENT_TIMESTAMP END,NEW.title);
    END""")
    conn.execute("""CREATE TRIGGER task_status_history AFTER UPDATE OF status ON tasks
        WHEN OLD.status != NEW.status BEGIN
        INSERT INTO task_lifecycle(task_id,event,occurred_at,estimate_hours,actual_minutes,title)
        VALUES (NEW.id,
            CASE WHEN NEW.status='Completed' THEN 'completed'
                 WHEN OLD.status='Completed' THEN 'reopened' ELSE 'status:' || NEW.status END,
            CURRENT_TIMESTAMP, NEW.estimated_hours,
            (WITH RECURSIVE family(id) AS (
                SELECT NEW.id UNION ALL
                SELECT t.id FROM tasks t JOIN family f ON t.parent_task_id=f.id
            ) SELECT COALESCE(SUM(minutes),0) FROM time_entries WHERE task_id IN (SELECT id FROM family)),
            NEW.title);
    END""")
