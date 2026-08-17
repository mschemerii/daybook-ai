from __future__ import annotations

from datetime import date

import pytest

from src.models.entities import Task
from src.services.task_service import TaskValidationError


def test_first_subtask_converts_parent_without_changing_original_fields(
    task_repo,
    task_service,
):
    parent = task_repo.create(
        Task(
            None,
            "Original project",
            description="Keep this description",
            priority="High",
            due_date=date(2026, 8, 20),
            source="Meeting notes",
            notes="Keep these notes",
            estimated_hours=24,
        )
    )

    child = task_service.add_subtask(
        parent.id,
        title="First step",
        estimated_hours=2.25,
    )
    converted = task_repo.get(parent.id)

    assert converted.task_type == "epic"
    assert child.parent_task_id == parent.id
    assert child.subtask_order == 0
    assert (
        converted.title,
        converted.description,
        converted.priority,
        converted.due_date,
        converted.source,
        converted.notes,
        converted.estimated_hours,
        converted.created_at,
        converted.updated_at,
    ) == (
        parent.title,
        parent.description,
        parent.priority,
        parent.due_date,
        parent.source,
        parent.notes,
        parent.estimated_hours,
        parent.created_at,
        parent.updated_at,
    )


def test_completed_subtasks_keep_parent_as_epic(task_repo, task_service):
    parent = task_service.create_task(title="Project")
    child = task_service.add_subtask(
        parent.id,
        title="Finished step",
        status="Completed",
    )

    assert task_repo.get(parent.id).task_type == "epic"
    assert task_repo.get(child.id).status == "Completed"


def test_removing_final_subtask_reverts_empty_epic(task_repo, task_service):
    parent = task_service.create_task(title="Project", estimated_hours=12)
    child = task_service.add_subtask(parent.id, title="Only step")

    detached = task_service.remove_subtask(child.id)

    assert detached.parent_task_id is None
    assert detached.subtask_order is None
    reverted = task_repo.get(parent.id)
    assert reverted.task_type == "standard"
    assert reverted.estimated_hours == 12


def test_epic_can_close_only_after_every_subtask_is_complete(
    task_repo,
    task_service,
):
    parent = task_service.create_task(title="Project")
    first = task_service.add_subtask(parent.id, title="Finished", status="Completed")
    second = task_service.add_subtask(parent.id, title="Still open")

    with pytest.raises(ValueError, match="Incomplete: Still open"):
        task_service.complete_task(parent.id)

    assert task_repo.get(parent.id).status == "Open"
    task_service.complete_task(second.id)
    closed = task_service.complete_task(parent.id)

    assert closed.status == "Completed"
    assert task_repo.get(first.id).status == "Completed"
    assert task_repo.get(parent.id).task_type == "epic"


def test_reopening_subtask_reopens_closed_epic(task_repo, task_service):
    parent = task_service.create_task(title="Project")
    child = task_service.add_subtask(
        parent.id,
        title="Finished",
        status="Completed",
    )
    task_service.complete_task(parent.id)

    reopened = task_service.reopen_task(child.id)

    assert reopened.status == "Open"
    assert task_repo.get(parent.id).status == "Open"


def test_reopening_nested_subtask_reopens_all_closed_ancestors(
    task_repo,
    task_service,
):
    root = task_service.create_task(title="Root")
    middle = task_service.add_subtask(root.id, title="Middle")
    leaf = task_service.add_subtask(middle.id, title="Leaf", status="Completed")
    task_service.complete_task(middle.id)
    task_service.complete_task(root.id)

    task_service.reopen_task(leaf.id)

    assert task_repo.get(middle.id).status == "Open"
    assert task_repo.get(root.id).status == "Open"


def test_epic_keeps_original_estimate_and_reports_child_total(
    task_repo,
    task_service,
):
    parent = task_service.create_task(title="Project", estimated_hours=20)
    task_service.add_subtask(parent.id, title="One", estimated_hours=1.25)
    task_service.add_subtask(parent.id, title="Two", estimated_hours=2.5)
    task_service.add_subtask(parent.id, title="Unknown")

    assert task_repo.get(parent.id).estimated_hours == 20
    assert task_repo.subtask_estimated_hours(parent.id) == 3.75


def test_reassigning_final_child_refreshes_both_parent_types(
    task_repo,
    task_service,
):
    first_parent = task_service.create_task(title="First project")
    second_parent = task_service.create_task(title="Second project")
    child = task_service.add_subtask(first_parent.id, title="Move me")

    moved = task_service.reassign_subtask(child.id, second_parent.id)

    assert moved.parent_task_id == second_parent.id
    assert moved.subtask_order == 0
    assert task_repo.get(first_parent.id).task_type == "standard"
    assert task_repo.get(second_parent.id).task_type == "epic"


def test_reassignment_rejects_hierarchy_cycles(task_service):
    root = task_service.create_task(title="Root")
    child = task_service.add_subtask(root.id, title="Child")
    grandchild = task_service.add_subtask(child.id, title="Grandchild")

    with pytest.raises(ValueError, match="descendants"):
        task_service.reassign_subtask(root.id, grandchild.id)


def test_reordering_is_stable_and_rejects_partial_lists(task_repo, task_service):
    parent = task_service.create_task(title="Project")
    first = task_service.add_subtask(parent.id, title="First")
    second = task_service.add_subtask(parent.id, title="Second")
    third = task_service.add_subtask(parent.id, title="Third")

    reordered = task_service.reorder_subtasks(
        parent.id,
        [third.id, first.id, second.id],
    )

    assert [task.id for task in reordered] == [third.id, first.id, second.id]
    assert [task.subtask_order for task in reordered] == [0, 1, 2]
    with pytest.raises(ValueError, match="every current subtask"):
        task_service.reorder_subtasks(parent.id, [first.id, second.id])
    assert [
        task.id for task in task_repo.list_subtasks(parent.id)
    ] == [third.id, first.id, second.id]


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"title": "x" * 51}, "50 characters"),
        ({"title": "Valid", "description": "x" * 4001}, "4,000 characters"),
        ({"title": "Valid", "estimated_hours": 1.1}, "quarter-hour"),
        ({"title": "Valid", "estimated_hours": 80.25}, "80 hours"),
    ],
)
def test_standard_task_validation_is_explicit(task_service, values, message):
    with pytest.raises(TaskValidationError, match=message):
        task_service.create_task(**values)


def test_epic_estimate_uses_epic_limit(task_service):
    parent = task_service.create_task(title="Project", estimated_hours=80)
    task_service.add_subtask(parent.id, title="Step")

    assert task_service.update_task(parent.id, {"estimated_hours": 999.75}).estimated_hours == 999.75
    with pytest.raises(TaskValidationError, match="1000 hours"):
        task_service.update_task(parent.id, {"estimated_hours": 1000.25})


def test_structural_fields_require_hierarchy_actions(task_service):
    task = task_service.create_task(title="Task")

    with pytest.raises(TaskValidationError, match="hierarchy actions"):
        task_service.update_task(task.id, {"task_type": "epic"})
