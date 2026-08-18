from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(slots=True)
class Task:
    id: int | None
    title: str
    description: str = ""
    priority: str = "Medium"
    due_date: date | None = None
    status: str = "Open"
    source: str = "User"
    notes: str = ""
    estimated_hours: float | None = None
    task_type: str = "standard"
    parent_task_id: int | None = None
    subtask_order: int | None = None
    provenance: str = "user_created"
    completion_criterion: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "status": self.status,
            "source": self.source,
            "notes": self.notes,
            "estimated_hours": self.estimated_hours,
            "task_type": self.task_type,
            "parent_task_id": self.parent_task_id,
            "subtask_order": self.subtask_order,
            "provenance": self.provenance,
            "completion_criterion": self.completion_criterion,
        }


@dataclass(slots=True)
class TaskDependency:
    dependent_task_id: int
    prerequisite_task_id: int
    created_at: datetime | None = None


@dataclass(slots=True)
class TimeEntry:
    id: int | None
    task_id: int
    work_date: date
    minutes: int
    note: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class DecompositionProposal:
    proposal_id: str
    parent_task_id: int
    payload_json: str
    fingerprint: str
    status: str = "draft"
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RankingFacts:
    """Application-owned facts supporting one deterministic focus result."""

    task_id: int
    calculated_focus_position: int
    user_priority: str
    status: str
    due_date: date | None
    is_overdue: bool
    due_proximity: str
    days_until_due: int | None
    estimated_hours: float | None
    incomplete_blockers: tuple[str, ...]
    deterministic_explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "calculated_focus_position": self.calculated_focus_position,
            "user_priority": self.user_priority,
            "status": self.status,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "is_overdue": self.is_overdue,
            "due_proximity": self.due_proximity,
            "days_until_due": self.days_until_due,
            "estimated_hours": self.estimated_hours,
            "incomplete_blockers": list(self.incomplete_blockers),
            "deterministic_explanation": self.deterministic_explanation,
        }


@dataclass(frozen=True, slots=True)
class DecompositionClassification:
    category: str
    reason: str
    prominent_recommendation: bool = False


@dataclass(frozen=True, slots=True)
class ReadinessAssessment:
    ready: bool
    missing_fields: tuple[str, ...]
    questions: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ProposedSubtask:
    item_key: str
    title: str
    description: str
    estimated_hours: float
    priority: str
    suggested_sequence: int
    completion_criterion: str
    due_date: date | None
    prerequisite_item_keys: tuple[str, ...]
    provenance: str = "ai_generated"

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_key": self.item_key,
            "title": self.title,
            "description": self.description,
            "estimated_hours": self.estimated_hours,
            "priority": self.priority,
            "suggested_sequence": self.suggested_sequence,
            "completion_criterion": self.completion_criterion,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "prerequisite_item_keys": list(self.prerequisite_item_keys),
            "provenance": self.provenance,
        }


@dataclass(frozen=True, slots=True)
class ProposalAdvisory:
    kind: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "message": self.message}


@dataclass(frozen=True, slots=True)
class ValidatedDecompositionProposal:
    proposal_type: str
    parent_task_id: int
    proposal_id: str
    summary: str
    requires_confirmation: bool
    subtasks: tuple[ProposedSubtask, ...]
    advisories: tuple[ProposalAdvisory, ...]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_type": self.proposal_type,
            "parent_task_id": self.parent_task_id,
            "proposal_id": self.proposal_id,
            "summary": self.summary,
            "requires_confirmation": self.requires_confirmation,
            "subtasks": [item.to_dict() for item in self.subtasks],
            "advisories": [item.to_dict() for item in self.advisories],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class ReviewItem:
    """Application-owned, proposal-local representation of a reviewed subtask."""

    item_key: str
    title: str
    description: str
    estimated_hours: float
    priority: str
    status: str
    completion_criterion: str
    due_date: date | None
    prerequisite_item_keys: tuple[str, ...]
    selected: bool
    display_order: int
    origin: str
    original_content: dict[str, Any] | None = None

    def content_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "estimated_hours": self.estimated_hours,
            "priority": self.priority,
            "status": self.status,
            "completion_criterion": self.completion_criterion,
            "due_date": self.due_date.isoformat() if self.due_date else None,
        }

    @property
    def provenance(self) -> str:
        if self.origin == "user":
            return "user_added_during_review"
        return (
            "ai_generated"
            if self.original_content == self.content_dict()
            else "ai_generated_user_edited"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_key": self.item_key,
            **self.content_dict(),
            "prerequisite_item_keys": list(self.prerequisite_item_keys),
            "selected": self.selected,
            "display_order": self.display_order,
            "origin": self.origin,
            "original_content": self.original_content,
        }


@dataclass(frozen=True, slots=True)
class ProposalReview:
    proposal_id: str
    parent_task_id: int
    summary: str
    status: str
    items: tuple[ReviewItem, ...]
    advisories: tuple[ProposalAdvisory, ...] = ()

    @property
    def selected_items(self) -> tuple[ReviewItem, ...]:
        return tuple(
            item
            for item in sorted(self.items, key=lambda value: value.display_order)
            if item.selected
        )


@dataclass(frozen=True, slots=True)
class ReviewValidation:
    review: ProposalReview
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    proposal_id: str
    parent_task_id: int
    item_task_ids: tuple[tuple[str, int], ...]
    repeated: bool = False

    @property
    def mapping(self) -> dict[str, int]:
        return dict(self.item_task_ids)


@dataclass(slots=True)
class JournalEntry:
    entry_date: date
    completed_today: str = ""
    in_progress: str = ""
    blocked_waiting: str = ""
    reflections: str = ""
    plan_tomorrow: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class ProposedAction:
    action: str
    proposed_values: dict[str, Any]
    reason: str
    requires_confirmation: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "requires_confirmation": self.requires_confirmation,
            "proposed_values": self.proposed_values,
            "reason": self.reason,
        }
