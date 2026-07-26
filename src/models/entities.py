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
        }


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
