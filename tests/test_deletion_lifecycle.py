import sqlite3
from datetime import date

import pytest


def test_plain_task_deletes_without_confirmation(task_service, task_repo):
    task = task_service.create_task(title="Disposable")
    task_service.delete_task(task.id)
    with pytest.raises(KeyError):
        task_repo.get(task.id)


def test_timed_task_requires_confirmation_and_cancel_changes_nothing(
    task_service, task_repo, time_entry_service
):
    task = task_service.create_task(title="Timed")
    entry = time_entry_service.create(task.id, work_date=date(2026, 8, 10), minutes=30)
    preview = task_service.deletion_preview(task.id)

    assert preview.deletes_recorded_time
    with pytest.raises(PermissionError, match="Confirm"):
        task_service.delete_task(task.id)
    assert task_repo.get(task.id).title == "Timed"
    assert time_entry_service.repo.get(entry.id).minutes == 30


def test_confirmed_timed_task_deletion_removes_entries_and_audits(
    task_service, task_repo, time_entry_service
):
    task = task_service.create_task(title="Timed")
    time_entry_service.create(task.id, work_date=date(2026, 8, 10), minutes=30)
    task_service.delete_task(task.id, confirmed=True)

    with pytest.raises(KeyError):
        task_repo.get(task.id)
    assert task_repo.deletion_audit()[-1]["deletion_action"] == "delete_task_with_time"


def test_epic_preview_names_preserved_and_deleted_subtasks(
    task_service, time_entry_service
):
    epic = task_service.create_task(title="Project")
    timed = task_service.add_subtask(epic.id, title="Keep my history")
    untimed = task_service.add_subtask(epic.id, title="Discard me")
    time_entry_service.create(timed.id, work_date=date(2026, 8, 10), minutes=30)

    preview = task_service.deletion_preview(epic.id)
    assert [task.title for task in preview.preserved_tasks] == ["Keep my history"]
    assert [task.title for task in preview.deleted_tasks] == ["Discard me"]
    assert not preview.deletes_recorded_time
    assert preview.requires_confirmation


def test_confirmed_epic_deletion_preserves_timed_descendants_as_regular_tasks(
    task_service, task_repo, time_entry_service
):
    epic = task_service.create_task(title="Project")
    branch = task_service.add_subtask(epic.id, title="Untimed branch")
    timed = task_service.add_subtask(branch.id, title="Keep my history")
    discarded = task_service.add_subtask(timed.id, title="No recorded work")
    time_entry_service.create(timed.id, work_date=date(2026, 8, 10), minutes=30)

    task_service.delete_task(epic.id, confirmed=True)

    with pytest.raises(KeyError):
        task_repo.get(epic.id)
    with pytest.raises(KeyError):
        task_repo.get(branch.id)
    with pytest.raises(KeyError):
        task_repo.get(discarded.id)
    preserved = task_repo.get(timed.id)
    assert preserved.parent_task_id is None
    assert preserved.subtask_order is None
    assert preserved.task_type == "standard"
    assert preserved.estimated_hours == timed.estimated_hours
    assert preserved.created_at == timed.created_at
    assert preserved.updated_at == timed.updated_at
    assert time_entry_service.recorded_minutes(timed.id) == 30


def test_epic_deletion_cancel_preserves_entire_hierarchy(task_service, task_repo):
    epic = task_service.create_task(title="Project")
    child = task_service.add_subtask(epic.id, title="Child")
    preview = task_service.deletion_preview(epic.id)

    assert preview.requires_confirmation
    assert task_repo.get(epic.id).task_type == "epic"
    assert task_repo.get(child.id).parent_task_id == epic.id


def test_epic_deletion_rolls_back_every_change_on_failure(
    task_service, task_repo, time_entry_service, db
):
    epic = task_service.create_task(title="Project")
    timed = task_service.add_subtask(epic.id, title="Timed")
    untimed = task_service.add_subtask(epic.id, title="Untimed")
    entry = time_entry_service.create(
        timed.id, work_date=date(2026, 8, 10), minutes=15
    )
    with db.connect() as conn:
        conn.execute(
            f"""
            CREATE TRIGGER reject_test_epic_deletion
            BEFORE DELETE ON tasks
            WHEN OLD.id = {epic.id}
            BEGIN
                SELECT RAISE(ABORT, 'simulated failure');
            END
            """
        )

    with pytest.raises(sqlite3.DatabaseError, match="simulated failure"):
        task_service.delete_task(epic.id, confirmed=True)

    assert task_repo.get(epic.id).task_type == "epic"
    assert task_repo.get(timed.id).parent_task_id == epic.id
    assert task_repo.get(untimed.id).parent_task_id == epic.id
    assert time_entry_service.repo.get(entry.id).minutes == 15
    assert task_repo.deletion_audit() == []
