from __future__ import annotations

from datetime import date

from src.repositories.journal_repository import JournalRepository
from src.repositories.task_repository import TaskRepository


class ContextService:
    """Builds deliberately small, provenance-rich context for the local model."""

    def __init__(self, tasks: TaskRepository, journals: JournalRepository):
        self.tasks = tasks
        self.journals = journals

    def build(self, include_tasks: bool, include_journal: bool, max_tasks: int = 8, max_journals: int = 2) -> tuple[list[dict], list[dict]]:
        records: list[dict] = []
        provenance: list[dict] = []
        if include_tasks:
            for task in self.tasks.list_all(include_completed=False)[:max_tasks]:
                record = {
                    "type": "task",
                    "id": task.id,
                    "title": task.title,
                    "priority": task.priority,
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                    "status": task.status,
                }
                records.append(record)
                provenance.append({"type": "task", "id": task.id, "label": task.title})
        if include_journal:
            for entry in self.journals.list_recent(max_journals):
                record = {
                    "type": "journal",
                    "date": entry.entry_date.isoformat(),
                    "in_progress": entry.in_progress[:500],
                    "blocked_waiting": entry.blocked_waiting[:500],
                    "reflections": entry.reflections[:500],
                }
                records.append(record)
                provenance.append({"type": "journal", "date": entry.entry_date.isoformat()})
        return records, provenance
