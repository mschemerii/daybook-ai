from datetime import date
import pytest

from src.models.reporting import ReportDataError
from src.repositories.reporting_repository import ReportingRepository
from src.repositories.reporting_settings_repository import ReportingSettingsRepository
from src.services.reporting_service import ReportingService
from src.utils.report_ranges import custom_range, monthly_range
from tests.helpers import insert_entry, insert_task


def service(db):
    return ReportingService(ReportingRepository(db))


def test_reporting_settings_round_trip(db):
    settings = ReportingSettingsRepository(db)
    assert settings.get_fiscal_start_month() == 1
    assert settings.set_fiscal_start_month(7) == 7
    assert settings.get_fiscal_start_month() == 7
    with pytest.raises(ValueError):
        settings.set_fiscal_start_month(0)


def test_report_builds_hierarchy_and_never_double_counts_epic_rollups(db):
    epic = insert_task(db, 'Reporting epic', estimated_hours=20, task_type='epic')
    child_a = insert_task(
        db, 'Range logic', estimated_hours=3, parent_task_id=epic, subtask_order=0
    )
    child_b = insert_task(
        db, 'PDF export', estimated_hours=4, parent_task_id=epic, subtask_order=1,
        task_type='epic'
    )
    grandchild = insert_task(
        db, 'PDF pagination', estimated_hours=2, parent_task_id=child_b, subtask_order=0
    )
    standalone = insert_task(db, 'Documentation', estimated_hours=1)
    insert_entry(db, child_a, date(2026, 9, 1), 120, 'range work')
    insert_entry(db, grandchild, date(2026, 9, 1), 90, 'pagination')
    insert_entry(db, standalone, date(2026, 9, 1), 30, 'docs')

    result = service(db).build_report(custom_range(date(2026, 9, 1), date(2026, 9, 1)))
    assert result.grand_total_minutes == 240
    assert [node.task.title for node in result.roots] == ['Reporting epic', 'Documentation']

    epic_node = result.roots[0]
    assert epic_node.task.estimated_hours == 20
    assert epic_node.subtask_estimated_hours == 7
    assert epic_node.direct_minutes == 0
    assert epic_node.cumulative_minutes == 210
    assert epic_node.display_minutes == 210
    assert [child.task.title for child in epic_node.children] == ['Range logic', 'PDF export']
    assert epic_node.children[0].display_minutes == 120
    assert epic_node.children[1].display_minutes == 90
    assert epic_node.children[1].children[0].display_minutes == 90
    assert sum(entry.minutes for entry in result.detailed_entries) == result.grand_total_minutes


def test_epic_cumulative_includes_any_actual_entry_recorded_on_epic_without_duplicate_total(db):
    epic = insert_task(db, 'Legacy epic', task_type='epic')
    child = insert_task(db, 'Child', parent_task_id=epic, subtask_order=0)
    insert_entry(db, epic, date(2026, 9, 1), 15, 'legacy direct epic entry')
    insert_entry(db, child, date(2026, 9, 1), 45, 'child entry')
    result = service(db).build_report(custom_range(date(2026, 9, 1), date(2026, 9, 1)))
    node = result.roots[0]
    assert node.direct_minutes == 15
    assert node.cumulative_minutes == 60
    assert node.display_minutes == 60
    assert result.grand_total_minutes == 60


def test_only_activity_tasks_and_required_ancestors_enter_report_hierarchy(db):
    epic = insert_task(db, 'Epic', task_type='epic')
    active_child = insert_task(db, 'Active', parent_task_id=epic, subtask_order=0)
    insert_task(db, 'Unrelated sibling', parent_task_id=epic, subtask_order=1)
    insert_task(db, 'Unrelated root')
    insert_entry(db, active_child, date(2026, 9, 1), 30)

    result = service(db).build_report(custom_range(date(2026, 9, 1), date(2026, 9, 1)))
    assert [node.task.title for node in result.iter_nodes()] == ['Epic', 'Active']


def test_detailed_entries_are_oldest_to_newest_then_stable_id(db):
    first_task = insert_task(db, 'First task')
    second_task = insert_task(db, 'Second task')
    later = insert_entry(db, first_task, date(2026, 9, 2), 10)
    same_day_first = insert_entry(db, second_task, date(2026, 9, 1), 20)
    same_day_second = insert_entry(db, first_task, date(2026, 9, 1), 30)

    result = service(db).build_report(custom_range(date(2026, 9, 1), date(2026, 9, 2)))
    assert [entry.id for entry in result.detailed_entries] == [
        same_day_first, same_day_second, later
    ]


def test_empty_range_returns_explicit_empty_report(db):
    insert_task(db, 'No time')
    result = service(db).build_report(custom_range(date(2026, 9, 1), date(2026, 9, 2)))
    assert result.roots == ()
    assert result.detailed_entries == ()
    assert result.grand_total_minutes == 0
    assert not result.has_activity


def test_deleted_tasks_and_cascaded_entries_do_not_appear(db):
    task = insert_task(db, 'Temporary')
    insert_entry(db, task, date(2026, 9, 1), 30)
    with db.connect() as conn:
        conn.execute('DELETE FROM tasks WHERE id = ?', (task,))
    result = service(db).build_report(custom_range(date(2026, 9, 1), date(2026, 9, 1)))
    assert result.detailed_entries == ()
    assert result.roots == ()


def test_current_tasks_in_progress_only_for_current_month_and_zero_month_time(db):
    due = date(2026, 9, 20)
    qualifies = insert_task(db, 'Needs work', due_date=due, status='Open')
    has_time = insert_task(db, 'Already worked', due_date=due, status='In Progress')
    insert_task(db, 'Done', due_date=due, status='Completed')
    insert_task(db, 'October work', due_date=date(2026, 10, 1), status='Open')
    insert_entry(db, has_time, date(2026, 9, 2), 15)

    current = service(db).build_report(monthly_range(date(2026, 9, 5)), today=date(2026, 9, 5))
    assert [task.id for task in current.current_tasks_in_progress] == [qualifies]

    other_month = service(db).build_report(monthly_range(date(2026, 8, 5)), today=date(2026, 9, 5))
    assert other_month.current_tasks_in_progress == ()
    daily = service(db).build_report(custom_range(date(2026, 9, 1), date(2026, 9, 30)), today=date(2026, 9, 5))
    assert daily.current_tasks_in_progress == ()


def test_current_tasks_in_progress_epic_uses_hierarchy_time(db):
    epic = insert_task(db, 'Due epic', due_date=date(2026, 9, 30), task_type='epic')
    child = insert_task(db, 'Worked child', parent_task_id=epic, subtask_order=0)
    insert_entry(db, child, date(2026, 9, 10), 30)
    result = service(db).build_report(monthly_range(date(2026, 9, 1)), today=date(2026, 9, 1))
    assert epic not in [task.id for task in result.current_tasks_in_progress]


def test_missing_parent_fails_loudly(db):
    with db.connect() as conn:
        conn.execute('PRAGMA foreign_keys = OFF')
        conn.execute(
            "INSERT INTO tasks(title, parent_task_id, subtask_order) VALUES ('Broken', 999, 0)"
        )
    with pytest.raises(ReportDataError, match='missing parent'):
        service(db).build_report(custom_range(date(2026, 9, 1), date(2026, 9, 1)))


def test_model_is_not_required_for_reporting_import_or_execution(db):
    task = insert_task(db, 'Offline task')
    insert_entry(db, task, date(2026, 9, 1), 10)
    result = service(db).build_report(custom_range(date(2026, 9, 1), date(2026, 9, 1)))
    assert result.grand_total_minutes == 10


def test_range_filter_is_inclusive_and_excludes_outside_entries(db):
    task = insert_task(db, 'Boundary task')
    outside = insert_entry(db, task, date(2026, 8, 31), 5)
    start = insert_entry(db, task, date(2026, 9, 1), 10)
    end = insert_entry(db, task, date(2026, 9, 2), 20)
    insert_entry(db, task, date(2026, 9, 3), 30)
    result = service(db).build_report(custom_range(date(2026, 9, 1), date(2026, 9, 2)))
    assert [entry.id for entry in result.detailed_entries] == [start, end]
    assert outside not in [entry.id for entry in result.detailed_entries]
    assert result.grand_total_minutes == 30


def test_malformed_persisted_work_date_fails_loudly_instead_of_being_skipped(db):
    task = insert_task(db, 'Malformed entry task')
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO time_entries(task_id, work_date, minutes, note) "
            "VALUES (?, 'not-a-date', 15, 'bad')",
            (task,),
        )
    with pytest.raises(ValueError):
        service(db).build_report(custom_range(date(2026, 9, 1), date(2026, 9, 30)))
