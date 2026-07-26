from __future__ import annotations

from datetime import date

from src.models.entities import ProposedAction, Task
from src.repositories.task_repository import TaskRepository
from src.utils.dates import format_date

PRIORITY_WEIGHT = {"High": 0, "Medium": 1, "Low": 2}
PROHIBITED_ACTIONS = {"send_email", "post_message", "browse_web", "run_command", "change_commitment"}
WRITE_ACTIONS = {"create_task", "edit_task", "complete_task", "delete_task"}


class TaskService:
    def __init__(self, repo: TaskRepository):
        self.repo = repo

    def create_task(self, **values) -> Task:
        return self.repo.create(Task(id=None, **values))

    def update_task(self, task_id: int, values: dict) -> Task:
        return self.repo.update(task_id, values)

    def complete_task(self, task_id: int) -> Task:
        return self.repo.update(task_id, {"status": "Completed"})

    def delete_task(self, task_id: int) -> None:
        self.repo.delete(task_id)

    def focus_items(self, today: date | None = None, limit: int = 3) -> list[Task]:
        today = today or date.today()
        tasks = [t for t in self.repo.list_all(include_completed=False) if t.status != "Blocked"]

        def key(task: Task):
            if task.due_date and task.due_date < today:
                bucket = 0
            elif task.due_date == today:
                bucket = 1
            else:
                bucket = 2
            due = task.due_date or date.max
            return bucket, PRIORITY_WEIGHT.get(task.priority, 99), due, task.id or 0

        return sorted(tasks, key=key)[:limit]

    def due_today(self, today: date | None = None) -> list[Task]:
        today = today or date.today()
        return [t for t in self.repo.list_all(False) if t.due_date == today and t.status != "Blocked"]

    def blocked(self) -> list[Task]:
        return [t for t in self.repo.list_all(False) if t.status == "Blocked"]

    def completed(self) -> list[Task]:
        """Return completed tasks, newest first."""
        return [
            task
            for task in self.repo.list_all(include_completed=True)
            if task.status == "Completed"
        ]

    def reopen_task(self, task_id: int) -> Task:
        """Return a completed task to Open status."""
        return self.repo.update(task_id, {"status": "Open"})

    @staticmethod
    def explain_rule_selection(task: Task, today: date | None = None) -> str:
        today = today or date.today()
        if task.due_date and task.due_date < today:
            return f"Overdue since {format_date(task.due_date)}; {task.priority.lower()} priority."
        if task.due_date == today:
            return f"Due today; {task.priority.lower()} priority."
        if task.due_date:
            return f"Upcoming due date {format_date(task.due_date)}; {task.priority.lower()} priority."
        return f"No due date; {task.priority.lower()} priority."

    @staticmethod
    def validate_proposal(proposal: ProposedAction) -> None:
        if proposal.action in PROHIBITED_ACTIONS:
            raise PermissionError(f"Action '{proposal.action}' is prohibited.")
        if proposal.action not in WRITE_ACTIONS:
            raise ValueError(f"Unsupported action '{proposal.action}'.")
        if not proposal.requires_confirmation:
            raise PermissionError("Write actions must require confirmation.")

    def apply_confirmed_proposal(self, proposal: ProposedAction) -> Task | None:
        self.validate_proposal(proposal)
        values = proposal.proposed_values
        if proposal.action == "create_task":
            return self.create_task(**values)
        task_id = int(values["task_id"])
        if proposal.action == "edit_task":
            return self.update_task(task_id, values.get("changes", {}))
        if proposal.action == "complete_task":
            return self.complete_task(task_id)
        if proposal.action == "delete_task":
            self.delete_task(task_id)
            return None
        raise ValueError("Unsupported proposal")
