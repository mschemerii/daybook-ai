from datetime import date

import pytest

from src.repositories.reporting_repository import ReportingRepository
from src.repositories.database import Database
from src.services.reporting_service import ReportingService
from src.utils.report_ranges import monthly_range


def record(db, task_id, minutes=30):
    with db.connect() as conn:
        conn.execute("INSERT INTO time_entries(task_id,work_date,minutes,note) VALUES (?,?,?,'test')",
                     (task_id, date.today().isoformat(), minutes))


def test_completion_requires_time_on_edit_and_complete(db, task_service):
    task = task_service.create_task(title='Work', estimated_hours=1)
    for action in (lambda: task_service.complete_task(task.id),
                   lambda: task_service.update_task(task.id, {'status': 'Completed'})):
        with pytest.raises(ValueError, match='Record time'):
            action()
    record(db, task.id)
    task_service.complete_task(task.id)
    report = ReportingService(ReportingRepository(db)).build_report(monthly_range(date.today()))
    assert report.completions[0]['actual_minutes'] == 30
    assert report.completions[0]['variance_minutes'] == -30
    assert report.completions[0]['blocked_minutes'] == 0


def test_closure_snapshot_preserved_on_reopen_and_estimate_change(db, task_service):
    task = task_service.create_task(title='Work', estimated_hours=1)
    record(db, task.id)
    task_service.complete_task(task.id)
    task_service.reopen_task(task.id)
    task_service.update_task(task.id, {'estimated_hours': 2})
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM task_lifecycle WHERE task_id=? ORDER BY id", (task.id,)).fetchall()
    assert [r['event'] for r in rows] == ['created', 'completed', 'reopened']
    assert rows[1]['estimate_hours'] == 1


def test_dependency_block_interval_closes_when_prerequisite_completes(db, task_service):
    prerequisite = task_service.create_task(title='Prerequisite')
    dependent = task_service.create_task(title='Dependent')
    task_service.add_dependency(dependent.id, prerequisite.id)
    record(db, prerequisite.id)
    task_service.complete_task(prerequisite.id)
    with db.connect() as conn:
        row = conn.execute('SELECT * FROM task_block_intervals WHERE task_id=?', (dependent.id,)).fetchone()
    assert row['reason'] == 'Prerequisite: Prerequisite'
    assert row['ended_at'] is not None


def test_epic_uses_descendant_time(db, task_service):
    epic = task_service.create_task(title='Epic')
    child = task_service.add_subtask(epic.id, title='Child')
    record(db, child.id, 45)
    task_service.complete_task(child.id)
    task_service.complete_task(epic.id)
    with db.connect() as conn:
        row = conn.execute("SELECT actual_minutes FROM task_lifecycle WHERE task_id=? AND event='completed'", (epic.id,)).fetchone()
    assert row[0] == 45


def test_v3_upgrade_preserves_legacy_status_without_inventing_date(tmp_path):
    import sqlite3
    from src.repositories.migrations import migrate, MIGRATIONS
    path = tmp_path / 'old.db'
    conn = sqlite3.connect(path)
    migrate(conn, path, migrations=MIGRATIONS[:3])
    conn.execute("INSERT INTO tasks(title,status) VALUES ('Legacy','Completed')")
    conn.commit()
    conn.close()
    db = Database(path)
    assert db.backup_path.exists()
    report = ReportingService(ReportingRepository(db)).build_report(monthly_range(date.today()))
    assert report.completions[0]['completed_at'] == 'Unknown (legacy)'
    assert report.completions[0]['actual_minutes'] is None
    with db.connect() as conn:
        assert conn.execute('SELECT status FROM tasks').fetchone()[0] == 'Completed'


def test_completion_uses_closure_period_and_all_recorded_effort(db, task_service):
    task = task_service.create_task(title='Cross-period work', estimated_hours=1)
    with db.connect() as conn:
        conn.execute("INSERT INTO time_entries(task_id,work_date,minutes,note) VALUES (?,'2020-01-01',30,'earlier work')", (task.id,))
    task_service.complete_task(task.id)
    report = ReportingService(ReportingRepository(db)).build_report(monthly_range(date.today()))
    assert report.grand_total_minutes == 0
    assert report.completions[0]['actual_minutes'] == 30
    assert report.has_activity


def test_overlapping_blockers_are_not_double_counted(db, task_service):
    task = task_service.create_task(title='Overlapping blocks')
    record(db, task.id)
    task_service.complete_task(task.id)
    with db.connect() as conn:
        conn.execute("UPDATE task_lifecycle SET occurred_at='2026-09-06 03:00:00' WHERE event='completed'")
        for key, start, end in [(1, '00:00:00', '02:00:00'), (2, '01:00:00', '03:00:00')]:
            conn.execute("INSERT INTO task_block_intervals(task_id,blocker_key,reason,started_at,ended_at) VALUES (?,?,'test',?,?)",
                         (task.id,key,'2026-09-06 '+start,'2026-09-06 '+end))
    report = ReportingService(ReportingRepository(db)).build_report(monthly_range(date(2026,9,1)))
    assert report.completions[0]['blocked_minutes'] == 180


def test_completion_exports_contain_history(db, task_service):
    import io
    import zipfile
    from src.services.report_export_service import ReportExportService
    task = task_service.create_task(title='Export closure')
    record(db, task.id)
    task_service.complete_task(task.id)
    report = ReportingService(ReportingRepository(db)).build_report(monthly_range(date.today()))
    exports = ReportExportService()
    with zipfile.ZipFile(io.BytesIO(exports.export_csv_zip(report))) as archive:
        assert b'Export closure' in archive.read('completions.csv')
    assert exports.export_summary_pdf(report).startswith(b'%PDF')
    assert exports.export_detailed_pdf(report).startswith(b'%PDF')
