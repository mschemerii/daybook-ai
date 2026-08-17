from datetime import date

import pytest

from src.services.time_entry_service import TimeEntryValidationError


def test_multiple_dated_entries_are_listed_and_totaled(task_service, time_entry_service):
    task = task_service.create_task(title="Build feature", estimated_hours=5)
    first = time_entry_service.create(task.id, work_date=date(2026, 8, 9), minutes=75)
    second = time_entry_service.create(task.id, work_date=date(2026, 8, 10), minutes=45)

    assert [entry.id for entry in time_entry_service.list_for_task(task.id)] == [first.id, second.id]
    assert time_entry_service.recorded_minutes(task.id) == 120
    assert task_service.repo.get(task.id).estimated_hours == 5


def test_time_entry_update_and_delete(task_service, time_entry_service):
    task = task_service.create_task(title="Task")
    entry = time_entry_service.create(task.id, work_date=date(2026, 8, 10), minutes=30)

    updated = time_entry_service.update(
        entry.id, work_date=date(2026, 8, 11), minutes=90, note="Revised"
    )
    assert (updated.work_date, updated.minutes, updated.note) == (
        date(2026, 8, 11), 90, "Revised"
    )
    time_entry_service.delete(entry.id)
    assert time_entry_service.list_for_task(task.id) == []


@pytest.mark.parametrize("minutes", [0, 721, -1, 1.5, True])
def test_entry_duration_validation(task_service, time_entry_service, minutes):
    task = task_service.create_task(title="Task")
    with pytest.raises(TimeEntryValidationError):
        time_entry_service.create(
            task.id, work_date=date(2026, 8, 10), minutes=minutes
        )


def test_daily_total_is_limited_across_tasks(task_service, time_entry_service):
    first = task_service.create_task(title="First")
    second = task_service.create_task(title="Second")
    time_entry_service.create(first.id, work_date=date(2026, 8, 10), minutes=720)
    time_entry_service.create(second.id, work_date=date(2026, 8, 10), minutes=720)

    with pytest.raises(TimeEntryValidationError, match="24 hours"):
        time_entry_service.create(first.id, work_date=date(2026, 8, 10), minutes=1)


def test_update_excludes_original_entry_from_daily_limit(task_service, time_entry_service):
    task = task_service.create_task(title="Task")
    entry = time_entry_service.create(task.id, work_date=date(2026, 8, 10), minutes=720)
    updated = time_entry_service.update(
        entry.id, work_date=date(2026, 8, 10), minutes=719
    )
    assert updated.minutes == 719


def test_epic_recorded_total_can_include_descendants(task_service, time_entry_service):
    epic = task_service.create_task(title="Epic")
    child = task_service.add_subtask(epic.id, title="Child")
    grandchild = task_service.add_subtask(child.id, title="Grandchild")
    time_entry_service.create(child.id, work_date=date(2026, 8, 10), minutes=20)
    time_entry_service.create(grandchild.id, work_date=date(2026, 8, 10), minutes=25)

    assert time_entry_service.recorded_minutes(epic.id) == 0
    assert time_entry_service.recorded_minutes(epic.id, include_descendants=True) == 45
