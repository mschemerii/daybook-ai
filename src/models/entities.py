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
