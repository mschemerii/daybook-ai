from __future__ import annotations

import json
from datetime import date

import pytest

from src.repositories.planning_repository import (
    ApprovalIntegrityError,
    PlanningRepository,
)
from src.services.planning_service import Phase7ValidationError, PlanningService
from tests.test_phase6_planning import FakeModel, ready_task, valid_payload


def make_service(task_repo, task_service, db):
    parent = ready_task(task_repo)
    service = PlanningService(
        task_service,
        PlanningRepository(db),
        FakeModel(
            proposal_factory=lambda contract: valid_payload(
                contract["parent_task_id"], contract["proposal_id"]
            )
        ),
    )
    proposal = service.request_decomposition(parent, {}).proposal
    return parent, service, proposal.proposal_id


def counts(db):
    with db.connect() as conn:
        return tuple(
            conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "tasks",
                "task_dependencies",
                "time_entries",
                "proposal_task_links",
            )
        )


def test_review_edits_restore_canonical_provenance_and_keep_stable_key(
    task_repo, task_service, db
):
    _, service, proposal_id = make_service(task_repo, task_service, db)
    original = service.get_review(proposal_id).items[0]
    service.update_review_item(
        proposal_id,
        original.item_key,
        {"title": "Edited research", "description": "Edited description"},
    )
    edited = service.get_review(proposal_id).items[0]
    assert edited.item_key == original.item_key
    assert edited.provenance == "ai_generated_user_edited"

    service.update_review_item(
        proposal_id,
        original.item_key,
        {"title": original.title, "description": original.description},
    )
    restored = service.get_review(proposal_id).items[0]
    assert restored.provenance == "ai_generated"


def test_manual_insert_remove_reorder_and_selection_preserve_keys(
    task_repo, task_service, db
):
    _, service, proposal_id = make_service(task_repo, task_service, db)
    review = service.add_review_item(
        proposal_id,
        title="Manual quality check",
        completion_criterion="Quality check is recorded.",
    )
    manual = review.items[-1]
    assert manual.item_key.startswith("manual-")
    assert manual.provenance == "user_added_during_review"
    service.reorder_review_items(
        proposal_id, [manual.item_key, "research", "draft"]
    )
    reordered = service.get_review(proposal_id)
    assert [item.item_key for item in reordered.items] == [
        manual.item_key,
        "research",
        "draft",
    ]
    assert all(item.provenance != "ai_generated_user_edited" for item in reordered.items)
    service.set_review_item_selected(proposal_id, manual.item_key, False)
    service.remove_review_item(proposal_id, manual.item_key)
    assert [item.item_key for item in service.get_review(proposal_id).items] == [
        "research",
        "draft",
    ]


def test_one_and_eight_selected_items_are_valid(task_repo, task_service, db):
    _, service, proposal_id = make_service(task_repo, task_service, db)
    service.set_review_prerequisites(proposal_id, "draft", [])
    service.set_review_item_selected(proposal_id, "research", False)
    assert len(service.validate_review(proposal_id).review.selected_items) == 1

    service.set_review_item_selected(proposal_id, "research", True)
    for index in range(6):
        service.add_review_item(
            proposal_id,
            title=f"Manual item {index}",
            completion_criterion="Done.",
        )
    assert len(service.validate_review(proposal_id).review.selected_items) == 8


def test_zero_and_nine_selected_items_are_rejected(task_repo, task_service, db):
    _, service, proposal_id = make_service(task_repo, task_service, db)
    service.set_review_item_selected(proposal_id, "research", False)
    service.set_review_item_selected(proposal_id, "draft", False)
    with pytest.raises(Phase7ValidationError, match="one and eight"):
        service.validate_review(proposal_id)

    service.set_review_item_selected(proposal_id, "research", True)
    service.set_review_item_selected(proposal_id, "draft", True)
    for index in range(7):
        service.add_review_item(
            proposal_id,
            title=f"Additional item {index}",
            completion_criterion="Done.",
        )
    with pytest.raises(Phase7ValidationError, match="one and eight"):
        service.validate_review(proposal_id)


@pytest.mark.parametrize("action", ["remove", "deselect"])
def test_removed_or_deselected_prerequisite_blocks_approval(
    task_repo, task_service, db, action
):
    _, service, proposal_id = make_service(task_repo, task_service, db)
    if action == "remove":
        service.remove_review_item(proposal_id, "research")
    else:
        service.set_review_item_selected(proposal_id, "research", False)
    with pytest.raises(Phase7ValidationError, match="removed or deselected"):
        service.approve_review(proposal_id)
    assert counts(db)[1:] == (0, 0, 0)


def test_prerequisite_duplicate_self_cycle_and_missing_are_rejected(
    task_repo, task_service, db
):
    _, service, proposal_id = make_service(task_repo, task_service, db)
    service.set_review_prerequisites(proposal_id, "draft", ["research", "research"])
    with pytest.raises(Phase7ValidationError, match="duplicate"):
        service.validate_review(proposal_id)
    service.set_review_prerequisites(proposal_id, "draft", ["draft"])
    with pytest.raises(Phase7ValidationError, match="itself"):
        service.validate_review(proposal_id)
    service.set_review_prerequisites(proposal_id, "draft", ["research"])
    service.set_review_prerequisites(proposal_id, "research", ["draft"])
    with pytest.raises(Phase7ValidationError, match="cycle"):
        service.validate_review(proposal_id)
    service.set_review_prerequisites(proposal_id, "research", ["missing"])
    with pytest.raises(Phase7ValidationError, match="removed or deselected"):
        service.validate_review(proposal_id)


def test_invalid_fields_are_rejected_and_warnings_recalculate(
    task_repo, task_service, db
):
    _, service, proposal_id = make_service(task_repo, task_service, db)
    with pytest.raises(Phase7ValidationError, match="Title is required"):
        service.update_review_item(proposal_id, "research", {"title": ""})
    with pytest.raises(Phase7ValidationError, match="quarter-hour"):
        service.update_review_item(
            proposal_id, "research", {"estimated_hours": 1.1}
        )
    service.update_review_item(
        proposal_id,
        "draft",
        {"due_date": date(2026, 8, 21), "estimated_hours": 1.0},
    )
    warnings = service.validate_review(proposal_id).warnings
    assert any("later than the parent" in warning for warning in warnings)
    assert any("Original estimate" in warning for warning in warnings)


def test_provenance_cannot_be_forged_and_parent_is_unchanged(
    task_repo, task_service, db
):
    parent, service, proposal_id = make_service(task_repo, task_service, db)
    with pytest.raises(Phase7ValidationError, match="Unsupported review fields"):
        service.update_review_item(
            proposal_id, "research", {"provenance": "user_created"}
        )
    stored = PlanningRepository(db).get(proposal_id)
    payload = json.loads(stored.payload_json)
    service.get_review(proposal_id)
    stored = PlanningRepository(db).get(proposal_id)
    payload = json.loads(stored.payload_json)
    # Materialize and then tamper only with persisted descriptive origin metadata.
    service.update_review_item(proposal_id, "research", {"title": "Changed"})
    stored = PlanningRepository(db).get(proposal_id)
    payload = json.loads(stored.payload_json)
    payload["review"]["items"][0]["origin"] = "user"
    PlanningRepository(db).update_payload(proposal_id, json.dumps(payload))
    with pytest.raises(Phase7ValidationError, match="provenance verification"):
        service.validate_review(proposal_id)
    assert task_repo.get(parent.id).provenance == parent.provenance


def test_atomic_approval_creates_order_hierarchy_dependencies_and_links(
    task_repo, task_service, dependency_repo, db
):
    parent, service, proposal_id = make_service(task_repo, task_service, db)
    service.add_review_item(
        proposal_id, title="Manual check", completion_criterion="Check complete."
    )
    manual_key = service.get_review(proposal_id).items[-1].item_key
    service.reorder_review_items(
        proposal_id, [manual_key, "research", "draft"]
    )
    result = service.approve_review(proposal_id)
    children = task_repo.list_subtasks(parent.id)
    assert [item.title for item in children] == [
        "Manual check",
        "Review source material",
        "Draft and review report",
    ]
    assert task_repo.get(parent.id).task_type == "epic"
    assert dependency_repo.exists(result.mapping["draft"], result.mapping["research"])
    assert [key for key, _ in result.item_task_ids] == [
        manual_key,
        "research",
        "draft",
    ]
    assert PlanningRepository(db).get(proposal_id).status == "approved"
    assert task_repo.get(parent.id).provenance == parent.provenance


@pytest.mark.parametrize(
    "failure_stage",
    [
        "validated",
        "task_created",
        "hierarchy_created",
        "dependency_created",
        "link_created",
        "status_updated",
    ],
)
def test_failures_at_material_stages_roll_back_everything(
    task_repo, task_service, db, failure_stage
):
    _, service, proposal_id = make_service(task_repo, task_service, db)
    before = counts(db)

    def fail(stage):
        if stage == failure_stage:
            raise RuntimeError(f"injected {stage}")

    with pytest.raises(RuntimeError, match="injected"):
        service.approve_review(proposal_id, failure_hook=fail)
    assert counts(db) == before
    assert PlanningRepository(db).get(proposal_id).status == "draft"


def test_repeated_and_fresh_service_approval_returns_original_mapping(
    task_repo, task_service, db
):
    _, service, proposal_id = make_service(task_repo, task_service, db)
    first = service.approve_review(proposal_id)
    second = service.approve_review(proposal_id)
    fresh = PlanningService(task_service, PlanningRepository(db), service.model)
    third = fresh.approve_review(proposal_id)
    assert first.mapping == second.mapping == third.mapping
    assert second.repeated and third.repeated
    assert counts(db) == (3, 1, 0, 2)


def test_inconsistent_approved_links_fail_without_recreating_tasks(
    task_repo, task_service, db
):
    _, service, proposal_id = make_service(task_repo, task_service, db)
    service.approve_review(proposal_id)
    with db.connect() as conn:
        conn.execute(
            "DELETE FROM proposal_task_links WHERE proposal_id = ? AND item_key = ?",
            (proposal_id, "research"),
        )
    before = counts(db)
    with pytest.raises(ApprovalIntegrityError, match="missing or inconsistent"):
        service.approve_review(proposal_id)
    assert counts(db) == before


@pytest.mark.parametrize("terminal", ["rejected", "cancelled"])
def test_rejection_and_cancellation_create_no_task_writes_and_are_terminal(
    task_repo, task_service, db, terminal
):
    _, service, proposal_id = make_service(task_repo, task_service, db)
    before = counts(db)
    if terminal == "rejected":
        service.reject_review(proposal_id)
    else:
        service.cancel_review(proposal_id)
    assert counts(db) == before
    with pytest.raises(ValueError, match="cannot be approved"):
        service.approve_review(proposal_id)
    with pytest.raises(Phase7ValidationError, match="cannot be edited"):
        service.update_review_item(proposal_id, "research", {"title": "No"})


def test_deleted_parent_blocks_application_without_writes(
    task_repo, task_service, db
):
    parent, service, proposal_id = make_service(task_repo, task_service, db)
    task_service.delete_task(parent.id)
    with pytest.raises(KeyError, match="Proposal"):
        service.approve_review(proposal_id)
    assert counts(db) == (0, 0, 0, 0)
