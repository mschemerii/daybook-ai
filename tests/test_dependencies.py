from __future__ import annotations

from datetime import date

import pytest

from src.services.task_service import ReopenConfirmationRequired


def test_dependency_creation_listing_and_removal(task_service):
    prerequisite = task_service.create_task(title="Prepare data")
    dependent = task_service.create_task(title="Run report")

    offer = task_service.add_dependency(dependent.id, prerequisite.id)

    assert offer is not None
    assert offer.kind == "create_epic"
    assert [task.id for task in task_service.prerequisites(dependent.id)] == [
        prerequisite.id
    ]
    assert [task.id for task in task_service.dependents(prerequisite.id)] == [
        dependent.id
    ]

    task_service.remove_dependency(dependent.id, prerequisite.id)

    assert task_service.prerequisites(dependent.id) == []
    assert task_service.dependents(prerequisite.id) == []
    assert not task_service.is_blocked(dependent.id)


def test_self_and_duplicate_dependencies_are_rejected(task_service):
    first = task_service.create_task(title="First")
    second = task_service.create_task(title="Second")

    with pytest.raises(ValueError, match="itself"):
        task_service.add_dependency(first.id, first.id)

    task_service.add_dependency(second.id, first.id)
    with pytest.raises(ValueError, match="already exists"):
        task_service.add_dependency(second.id, first.id)


def test_direct_dependency_cycle_is_rejected(task_service):
    first = task_service.create_task(title="First")
    second = task_service.create_task(title="Second")
    task_service.add_dependency(second.id, first.id)

    with pytest.raises(ValueError, match="cycle"):
        task_service.add_dependency(first.id, second.id)


def test_indirect_dependency_cycle_is_rejected(task_service):
    first = task_service.create_task(title="First")
    second = task_service.create_task(title="Second")
    third = task_service.create_task(title="Third")
    task_service.add_dependency(second.id, first.id)
    task_service.add_dependency(third.id, second.id)

    with pytest.raises(ValueError, match="cycle"):
        task_service.add_dependency(first.id, third.id)


def test_one_incomplete_prerequisite_blocks_and_names_task(task_service):
    prerequisite = task_service.create_task(title="Approve copy")
    dependent = task_service.create_task(title="Publish copy")
    task_service.add_dependency(dependent.id, prerequisite.id)

    blockers = task_service.blocking_prerequisites(dependent.id)

    assert [task.title for task in blockers] == ["Approve copy"]
    assert task_service.is_blocked(dependent.id)
    assert [task.id for task in task_service.blocked()] == [dependent.id]


def test_multiple_prerequisites_block_until_every_one_completes(task_service):
    first = task_service.create_task(title="Legal review")
    second = task_service.create_task(title="Security review")
    dependent = task_service.create_task(title="Release")
    task_service.add_dependency(dependent.id, first.id)
    task_service.add_dependency(dependent.id, second.id)

    assert {task.id for task in task_service.blocking_prerequisites(dependent.id)} == {
        first.id,
        second.id,
    }

    task_service.complete_task(first.id)

    assert [
        task.id for task in task_service.blocking_prerequisites(dependent.id)
    ] == [second.id]
    assert task_service.is_blocked(dependent.id)

    task_service.complete_task(second.id)

    assert task_service.blocking_prerequisites(dependent.id) == []
    assert not task_service.is_blocked(dependent.id)


def test_blocked_task_cannot_be_completed(task_service, task_repo):
    prerequisite = task_service.create_task(title="Prerequisite")
    dependent = task_service.create_task(title="Dependent")
    task_service.add_dependency(dependent.id, prerequisite.id)

    with pytest.raises(ValueError, match="Prerequisite"):
        task_service.complete_task(dependent.id)

    assert task_repo.get(dependent.id).status == "Open"


def test_status_update_cannot_bypass_completion_guard(task_service, task_repo):
    prerequisite = task_service.create_task(title="Prerequisite")
    dependent = task_service.create_task(title="Dependent")
    task_service.add_dependency(dependent.id, prerequisite.id)

    with pytest.raises(ValueError, match="Prerequisite"):
        task_service.update_task(dependent.id, {"status": "Completed"})

    assert task_repo.get(dependent.id).status == "Open"


def test_removing_one_dependency_recalculates_remaining_blockers(task_service):
    first = task_service.create_task(title="First")
    second = task_service.create_task(title="Second")
    dependent = task_service.create_task(title="Dependent")
    task_service.add_dependency(dependent.id, first.id)
    task_service.add_dependency(dependent.id, second.id)

    task_service.remove_dependency(dependent.id, first.id)

    assert [
        task.id for task in task_service.blocking_prerequisites(dependent.id)
    ] == [second.id]
    assert task_service.is_blocked(dependent.id)


def test_direct_reopening_cascade_requires_confirmation(task_service, task_repo):
    prerequisite = task_service.create_task(title="Approved", status="Completed")
    dependent = task_service.create_task(title="Released", status="Completed")
    task_service.add_dependency(dependent.id, prerequisite.id)

    with pytest.raises(ReopenConfirmationRequired) as warning:
        task_service.reopen_task(prerequisite.id)

    assert [task.title for task in warning.value.affected_tasks] == ["Released"]
    assert task_repo.get(prerequisite.id).status == "Completed"
    assert task_repo.get(dependent.id).status == "Completed"

    task_service.reopen_task(
        prerequisite.id,
        confirm_dependency_cascade=True,
    )

    assert task_repo.get(prerequisite.id).status == "Open"
    assert task_repo.get(dependent.id).status == "Open"
    assert task_service.is_blocked(dependent.id)


def test_transitive_reopening_cascade_names_and_reopens_every_dependent(
    task_service,
    task_repo,
):
    first = task_service.create_task(title="Design", status="Completed")
    second = task_service.create_task(title="Build", status="Completed")
    third = task_service.create_task(title="Ship", status="Completed")
    task_service.add_dependency(second.id, first.id)
    task_service.add_dependency(third.id, second.id)

    with pytest.raises(ReopenConfirmationRequired) as warning:
        task_service.reopen_task(first.id)

    assert [task.title for task in warning.value.affected_tasks] == ["Build", "Ship"]
    assert "Build" in str(warning.value)
    assert "Ship" in str(warning.value)

    task_service.reopen_task(first.id, confirm_dependency_cascade=True)

    assert task_repo.get(second.id).status == "Open"
    assert task_repo.get(third.id).status == "Open"
    assert task_service.is_blocked(second.id)
    assert task_service.is_blocked(third.id)


def test_reopen_preview_is_a_cancel_path_with_no_record_changes(
    task_service,
    task_repo,
    dependency_repo,
):
    prerequisite = task_service.create_task(title="Approved", status="Completed")
    dependent = task_service.create_task(title="Released", status="Completed")
    dependency_repo.create(dependent.id, prerequisite.id)
    before = {
        task.id: (task.status, task.updated_at)
        for task in task_repo.list_all(include_completed=True)
    }

    affected = task_service.reopen_affected_tasks(prerequisite.id)

    assert [task.id for task in affected] == [dependent.id]
    after = {
        task.id: (task.status, task.updated_at)
        for task in task_repo.list_all(include_completed=True)
    }
    assert after == before


def test_already_open_dependent_stays_open_and_becomes_blocked(
    task_service,
    task_repo,
):
    prerequisite = task_service.create_task(title="Approved", status="Completed")
    dependent = task_service.create_task(title="Follow-up", status="Open")
    task_service.add_dependency(dependent.id, prerequisite.id)

    task_service.reopen_task(
        prerequisite.id,
        confirm_dependency_cascade=True,
    )

    assert task_repo.get(dependent.id).status == "Open"
    assert task_service.is_blocked(dependent.id)


def test_dependency_cascade_preserves_subtask_ancestor_reopening(
    task_service,
    task_repo,
):
    epic = task_service.create_task(title="Epic")
    prerequisite = task_service.add_subtask(
        epic.id,
        title="Epic step",
        status="Completed",
    )
    dependent = task_service.create_task(title="Outside task", status="Completed")
    task_service.complete_task(epic.id)
    task_service.add_dependency(dependent.id, prerequisite.id)

    task_service.reopen_task(
        prerequisite.id,
        confirm_dependency_cascade=True,
    )

    assert task_repo.get(epic.id).status == "Open"
    assert task_repo.get(prerequisite.id).status == "Open"
    assert task_repo.get(dependent.id).status == "Open"


def test_dependency_between_ancestor_and_subtask_is_rejected(task_service):
    parent = task_service.create_task(title="Parent")
    child = task_service.add_subtask(parent.id, title="Child")

    with pytest.raises(ValueError, match="ancestor"):
        task_service.add_dependency(parent.id, child.id)
    with pytest.raises(ValueError, match="ancestor"):
        task_service.add_dependency(child.id, parent.id)


def test_hierarchy_change_that_conflicts_with_dependency_is_rejected(task_service):
    future_parent = task_service.create_task(title="Future parent")
    child = task_service.create_task(title="Future child")
    task_service.add_dependency(future_parent.id, child.id)

    with pytest.raises(ValueError, match="ancestor"):
        task_service.reassign_subtask(child.id, future_parent.id)


def test_hierarchy_change_rejects_dependency_on_a_moved_descendant(task_service):
    future_parent = task_service.create_task(title="Future parent")
    moving_root = task_service.create_task(title="Moving root")
    descendant = task_service.add_subtask(moving_root.id, title="Descendant")
    task_service.add_dependency(future_parent.id, descendant.id)

    with pytest.raises(ValueError, match="ancestor"):
        task_service.reassign_subtask(moving_root.id, future_parent.id)


def test_standalone_dependency_returns_epic_offer_with_suggested_name(task_service):
    prerequisite = task_service.create_task(title="Draft")
    dependent = task_service.create_task(title="Publish")

    offer = task_service.add_dependency(dependent.id, prerequisite.id)

    assert offer.kind == "create_epic"
    assert offer.suggested_epic_name == "Draft then Publish"
    assert task_service.prerequisites(dependent.id)[0].id == prerequisite.id


@pytest.mark.parametrize(
    ("use_custom_name", "expected_name"),
    [(False, "Draft then Publish"), (True, "Publication workflow")],
)
def test_epic_offer_accepts_suggested_or_replacement_name(
    task_service,
    task_repo,
    use_custom_name,
    expected_name,
):
    prerequisite = task_service.create_task(title="Draft")
    dependent = task_service.create_task(title="Publish")
    offer = task_service.add_dependency(dependent.id, prerequisite.id)
    chosen_name = (
        "Publication workflow" if use_custom_name else offer.suggested_epic_name
    )

    epic = task_service.convert_dependency_pair_to_epic(
        dependent.id,
        prerequisite.id,
        chosen_name,
    )

    assert epic.title == expected_name
    assert epic.task_type == "epic"
    assert [task.id for task in task_repo.list_subtasks(epic.id)] == [
        prerequisite.id,
        dependent.id,
    ]
    assert task_service.prerequisites(dependent.id)[0].id == prerequisite.id


def test_declining_epic_offer_leaves_dependency_and_hierarchy_unchanged(task_service):
    prerequisite = task_service.create_task(title="Draft")
    dependent = task_service.create_task(title="Publish")
    offer = task_service.add_dependency(dependent.id, prerequisite.id)

    assert offer.kind == "create_epic"
    assert task_service.repo.get(prerequisite.id).parent_task_id is None
    assert task_service.repo.get(dependent.id).parent_task_id is None
    assert task_service.prerequisites(dependent.id)[0].id == prerequisite.id


def test_standalone_dependent_is_appended_to_epic_only_after_approval(
    task_service,
    task_repo,
):
    epic = task_service.create_task(title="Release epic")
    first_step = task_service.add_subtask(epic.id, title="First step")
    dependent = task_service.create_task(title="Final check")

    offer = task_service.add_dependency(dependent.id, epic.id)

    assert offer.kind == "append_to_epic"
    assert task_repo.get(dependent.id).parent_task_id is None
    assert task_service.prerequisites(dependent.id)[0].id == epic.id

    moved = task_service.append_dependent_to_epic(dependent.id, epic.id)

    assert moved.parent_task_id == epic.id
    assert moved.subtask_order == 1
    assert [task.id for task in task_repo.list_subtasks(epic.id)] == [
        first_step.id,
        dependent.id,
    ]
    assert task_service.prerequisites(dependent.id) == []


def test_append_conversion_has_no_parent_dependency_deadlock(
    task_service,
    task_repo,
):
    epic = task_service.create_task(title="Release epic")
    first_step = task_service.add_subtask(
        epic.id,
        title="First step",
        status="Completed",
    )
    dependent = task_service.create_task(title="Final check")
    task_service.add_dependency(dependent.id, epic.id)
    task_service.append_dependent_to_epic(dependent.id, epic.id)

    task_service.complete_task(dependent.id)
    completed_epic = task_service.complete_task(epic.id)

    assert task_repo.get(first_step.id).status == "Completed"
    assert completed_epic.status == "Completed"


def test_append_to_completed_nested_epic_reopens_completed_ancestors(
    task_service,
    task_repo,
):
    root = task_service.create_task(title="Root epic")
    inner = task_service.add_subtask(root.id, title="Inner epic")
    original_step = task_service.add_subtask(
        inner.id,
        title="Original step",
        status="Completed",
    )
    task_service.complete_task(inner.id)
    task_service.complete_task(root.id)
    dependent = task_service.create_task(title="New final step")
    task_service.add_dependency(dependent.id, inner.id)

    task_service.append_dependent_to_epic(dependent.id, inner.id)

    assert task_repo.get(original_step.id).status == "Completed"
    assert task_repo.get(inner.id).status == "Open"
    assert task_repo.get(root.id).status == "Open"


def test_unrelated_existing_task_data_remains_unchanged(task_service, task_repo):
    existing = task_service.create_task(
        title="Existing migrated task",
        description="Preserve exactly",
        priority="High",
        due_date=date(2026, 8, 20),
        status="In Progress",
        source="Migration",
        notes="Original notes",
        estimated_hours=4.25,
        completion_criterion="Reviewed",
    )
    before = task_repo.get(existing.id)
    prerequisite = task_service.create_task(title="New prerequisite")
    dependent = task_service.create_task(title="New dependent")

    task_service.add_dependency(dependent.id, prerequisite.id)
    task_service.remove_dependency(dependent.id, prerequisite.id)

    after = task_repo.get(existing.id)
    assert after.to_dict() == before.to_dict()
    assert after.created_at == before.created_at
    assert after.updated_at == before.updated_at
