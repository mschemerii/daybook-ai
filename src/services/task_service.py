from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass

from src.models.entities import ProposedAction, RankingFacts, Task
from src.repositories.dependency_repository import DependencyRepository
from src.repositories.task_repository import TaskRepository
from src.utils.dates import format_date

PRIORITY_WEIGHT = {"High": 0, "Medium": 1, "Low": 2}
PROHIBITED_ACTIONS = {"send_email", "post_message", "browse_web", "run_command", "change_commitment"}
WRITE_ACTIONS = {"create_task", "edit_task", "complete_task", "delete_task"}
TITLE_MAX_LENGTH = 50
DESCRIPTION_MAX_LENGTH = 4_000
STANDARD_ESTIMATE_MAX_HOURS = Decimal("1000")
EPIC_ESTIMATE_MAX_HOURS = Decimal("1000")
VALID_PRIORITIES = {"High", "Medium", "Low"}
VALID_STATUSES = {"Open", "In Progress", "Blocked", "Completed"}


class TaskValidationError(ValueError):
    """Raised when user-provided task values fail deterministic validation."""


@dataclass(frozen=True, slots=True)
class DependencyOffer:
    kind: str
    dependent_task_id: int
    prerequisite_task_id: int
    suggested_epic_name: str | None = None


@dataclass(frozen=True, slots=True)
class DeletionPreview:
    task: Task
    preserved_tasks: tuple[Task, ...]
    deleted_tasks: tuple[Task, ...]
    deletes_recorded_time: bool

    @property
    def requires_confirmation(self) -> bool:
        return self.task.task_type == "epic" or self.deletes_recorded_time


class ReopenConfirmationRequired(ValueError):
    """Raised before a dependency reopening cascade changes any records."""

    def __init__(self, task: Task, affected_tasks: list[Task]):
        self.task = task
        self.affected_tasks = affected_tasks
        names = ", ".join(
            f"{affected.title} (task {affected.id})"
            for affected in affected_tasks
        )
        super().__init__(
            f"Reopening {task.title} affects these dependent tasks: {names}"
        )


class TaskService:
    def __init__(
        self,
        repo: TaskRepository,
        dependencies: DependencyRepository | None = None,
    ):
        self.repo = repo
        self.dependencies = dependencies or DependencyRepository(repo.db)

    def create_task(self, **values) -> Task:
        values = dict(values)
        for structural_field in ("task_type", "parent_task_id", "subtask_order"):
            values.pop(structural_field, None)
        self._validate_values(values, task_type="standard", require_title=True)
        return self.repo.create(Task(id=None, **values))

    def update_task(self, task_id: int, values: dict) -> Task:
        current = self.repo.get(task_id)
        values = dict(values)
        prohibited = {"task_type", "parent_task_id", "subtask_order"} & values.keys()
        if prohibited:
            names = ", ".join(sorted(prohibited))
            raise TaskValidationError(
                f"Use hierarchy actions to change structural fields: {names}"
            )
        merged = current.to_dict()
        merged.update(values)
        self._validate_values(
            merged,
            task_type=current.task_type,
            require_title=True,
        )
        requested_status = values.get("status")
        if current.status == "Completed" and requested_status not in (
            None,
            "Completed",
        ):
            raise TaskValidationError(
                "Use the Reopen action so affected dependent tasks can be confirmed."
            )
        if requested_status == "Completed" and current.status != "Completed":
            blockers = self.blocking_prerequisites(task_id)
            if blockers:
                names = ", ".join(
                    f"{task.title} (task {task.id})" for task in blockers
                )
                raise TaskValidationError(
                    "Complete every prerequisite before closing this task. "
                    f"Incomplete: {names}"
                )
        return self.repo.update(task_id, values)

    def add_subtask(self, parent_task_id: int, **values) -> Task:
        self.repo.get(parent_task_id)
        values = dict(values)
        for structural_field in ("task_type", "parent_task_id", "subtask_order"):
            values.pop(structural_field, None)
        self._validate_values(values, task_type="standard", require_title=True)
        return self.repo.add_subtask(parent_task_id, Task(id=None, **values))

    def remove_subtask(self, task_id: int) -> Task:
        return self.repo.detach_subtask(task_id)

    def reassign_subtask(self, task_id: int, parent_task_id: int) -> Task:
        self._validate_hierarchy_assignment(task_id, parent_task_id)
        return self.repo.reassign_subtask(task_id, parent_task_id)

    def reorder_subtasks(
        self,
        parent_task_id: int,
        ordered_task_ids: list[int],
    ) -> list[Task]:
        return self.repo.reorder_subtasks(parent_task_id, ordered_task_ids)

    def move_subtask(self, task_id: int, direction: int) -> list[Task]:
        if direction not in (-1, 1):
            raise ValueError("Subtasks can move only one position at a time")
        task = self.repo.get(task_id)
        if task.parent_task_id is None:
            raise ValueError("Task is not a subtask")
        children = self.repo.list_subtasks(task.parent_task_id)
        child_ids = [child.id for child in children]
        current_index = child_ids.index(task_id)
        new_index = current_index + direction
        if new_index < 0 or new_index >= len(child_ids):
            return children
        child_ids[current_index], child_ids[new_index] = (
            child_ids[new_index],
            child_ids[current_index],
        )
        return self.repo.reorder_subtasks(task.parent_task_id, child_ids)

    def complete_task(self, task_id: int) -> Task:
        blockers = self.blocking_prerequisites(task_id)
        if blockers:
            names = ", ".join(
                f"{task.title} (task {task.id})" for task in blockers
            )
            raise ValueError(
                "Complete every prerequisite before closing this task. "
                f"Incomplete: {names}"
            )
        return self.repo.update(task_id, {"status": "Completed"})

    def deletion_preview(self, task_id: int) -> DeletionPreview:
        task, descendants, timed_ids = self.repo.deletion_details(task_id)
        preserved = tuple(item for item in descendants if item.id in timed_ids)
        deleted = tuple(item for item in descendants if item.id not in timed_ids)
        return DeletionPreview(
            task,
            preserved,
            deleted,
            task.id in timed_ids,
        )

    def delete_task(self, task_id: int, *, confirmed: bool = False) -> None:
        preview = self.deletion_preview(task_id)
        if preview.requires_confirmation and not confirmed:
            raise PermissionError("Confirm the deletion preview before deleting this task.")
        self.repo.governed_delete(task_id)

    def focus_items(self, today: date | None = None, limit: int = 3) -> list[Task]:
        today = today or date.today()
        tasks = [
            task
            for task in self.repo.list_all(include_completed=False)
            if not self.is_blocked(task.id)
        ]

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

    def ranking_facts(
        self,
        task: Task,
        calculated_position: int,
        today: date | None = None,
    ) -> RankingFacts:
        """Return typed application facts without asking AI to rank anything."""
        today = today or date.today()
        days_until_due = (
            (task.due_date - today).days if task.due_date is not None else None
        )
        if days_until_due is None:
            due_proximity = "no_due_date"
        elif days_until_due < 0:
            due_proximity = "overdue"
        elif days_until_due == 0:
            due_proximity = "due_today"
        else:
            due_proximity = "upcoming"
        blockers = tuple(
            f"{item.title} (task {item.id})"
            for item in self.blocking_prerequisites(task.id)
        )
        return RankingFacts(
            task_id=int(task.id),
            calculated_focus_position=calculated_position,
            user_priority=task.priority,
            status=task.status,
            due_date=task.due_date,
            is_overdue=bool(days_until_due is not None and days_until_due < 0),
            due_proximity=due_proximity,
            days_until_due=days_until_due,
            estimated_hours=task.estimated_hours,
            incomplete_blockers=blockers,
            deterministic_explanation=self.explain_rule_selection(task, today),
        )

    def due_today(self, today: date | None = None) -> list[Task]:
        today = today or date.today()
        return [
            task
            for task in self.repo.list_all(False)
            if task.due_date == today and not self.is_blocked(task.id)
        ]

    def blocked(self) -> list[Task]:
        return [
            task
            for task in self.repo.list_all(False)
            if self.is_blocked(task.id)
        ]

    def completed(self) -> list[Task]:
        """Return completed tasks, newest first."""
        return [
            task
            for task in self.repo.list_all(include_completed=True)
            if task.status == "Completed"
        ]

    def reopen_task(
        self,
        task_id: int,
        *,
        confirm_dependency_cascade: bool = False,
    ) -> Task:
        """Return a task to Open, requiring confirmation for dependents."""
        task = self.repo.get(task_id)
        affected = self.reopen_affected_tasks(task_id)
        if affected and not confirm_dependency_cascade:
            raise ReopenConfirmationRequired(task, affected)
        if affected:
            return self.dependencies.reopen_cascade(task_id)
        return self.repo.update(task_id, {"status": "Open"})

    def prerequisites(self, task_id: int) -> list[Task]:
        self.repo.get(task_id)
        return self.dependencies.prerequisite_tasks(task_id)

    def dependents(self, task_id: int) -> list[Task]:
        self.repo.get(task_id)
        return self.dependencies.dependent_tasks(task_id)

    def blocking_prerequisites(self, task_id: int) -> list[Task]:
        self.repo.get(task_id)
        return self.dependencies.incomplete_prerequisites(task_id)

    def is_blocked(self, task_id: int) -> bool:
        task = self.repo.get(task_id)
        return task.status == "Blocked" or bool(
            self.dependencies.incomplete_prerequisites(task_id)
        )

    def reopen_affected_tasks(self, task_id: int) -> list[Task]:
        self.repo.get(task_id)
        return self.dependencies.affected_dependents(task_id)

    def add_dependency(
        self,
        dependent_task_id: int,
        prerequisite_task_id: int,
    ) -> DependencyOffer | None:
        dependent = self.repo.get(dependent_task_id)
        prerequisite = self.repo.get(prerequisite_task_id)
        if dependent_task_id == prerequisite_task_id:
            raise ValueError("A task cannot depend on itself")
        if self.dependencies.exists(dependent_task_id, prerequisite_task_id):
            raise ValueError("That dependency already exists")
        if dependent.status == "Completed" and prerequisite.status != "Completed":
            raise ValueError(
                "Reopen the dependent task before adding an incomplete prerequisite"
            )

        dependent_descendants = self.repo.descendant_ids(dependent_task_id)
        prerequisite_descendants = self.repo.descendant_ids(prerequisite_task_id)
        if (
            prerequisite_task_id in dependent_descendants
            or dependent_task_id in prerequisite_descendants
        ):
            raise ValueError(
                "A dependency cannot connect an ancestor and its subtask"
            )

        adjacency = self._combined_adjacency()
        if self._reachable(prerequisite_task_id, dependent_task_id, adjacency):
            raise ValueError(
                "That dependency would create a dependency or hierarchy cycle"
            )

        self.dependencies.create(dependent_task_id, prerequisite_task_id)

        if self._is_standalone_regular(dependent) and self._is_standalone_regular(
            prerequisite
        ):
            return DependencyOffer(
                "create_epic",
                dependent_task_id,
                prerequisite_task_id,
                self.suggest_epic_name(prerequisite.title, dependent.title),
            )
        if self._is_standalone_regular(dependent) and prerequisite.task_type == "epic":
            return DependencyOffer(
                "append_to_epic",
                dependent_task_id,
                prerequisite_task_id,
            )
        return None

    def remove_dependency(
        self,
        dependent_task_id: int,
        prerequisite_task_id: int,
    ) -> None:
        self.repo.get(dependent_task_id)
        self.repo.get(prerequisite_task_id)
        self.dependencies.delete(dependent_task_id, prerequisite_task_id)

    def convert_dependency_pair_to_epic(
        self,
        dependent_task_id: int,
        prerequisite_task_id: int,
        epic_title: str,
    ) -> Task:
        title = epic_title.strip()
        self._validate_values(
            {"title": title},
            task_type="epic",
            require_title=True,
        )
        return self.dependencies.convert_pair_to_epic(
            dependent_task_id,
            prerequisite_task_id,
            title,
        )

    def append_dependent_to_epic(
        self,
        dependent_task_id: int,
        epic_task_id: int,
    ) -> Task:
        return self.dependencies.append_dependent_to_epic(
            dependent_task_id,
            epic_task_id,
        )

    @staticmethod
    def suggest_epic_name(prerequisite_title: str, dependent_title: str) -> str:
        suggestion = f"{prerequisite_title} then {dependent_title}"
        if len(suggestion) <= TITLE_MAX_LENGTH:
            return suggestion
        return suggestion[: TITLE_MAX_LENGTH - 1].rstrip() + "…"

    @staticmethod
    def _is_standalone_regular(task: Task) -> bool:
        return task.task_type == "standard" and task.parent_task_id is None

    def _combined_adjacency(self) -> dict[int, set[int]]:
        tasks = self.repo.list_all(include_completed=True)
        adjacency = {int(task.id): set() for task in tasks}
        for task in tasks:
            if task.parent_task_id is not None:
                adjacency[int(task.parent_task_id)].add(int(task.id))
        for dependent_id, prerequisite_id in self.dependencies.dependency_pairs():
            adjacency.setdefault(dependent_id, set()).add(prerequisite_id)
        return adjacency

    @staticmethod
    def _reachable(
        start: int,
        target: int,
        adjacency: dict[int, set[int]],
    ) -> bool:
        pending = [start]
        visited: set[int] = set()
        while pending:
            current = pending.pop()
            if current == target:
                return True
            if current in visited:
                continue
            visited.add(current)
            pending.extend(adjacency.get(current, ()))
        return False

    def _validate_hierarchy_assignment(
        self,
        task_id: int,
        parent_task_id: int,
    ) -> None:
        task = self.repo.get(task_id)
        self.repo.get(parent_task_id)
        if task.parent_task_id == parent_task_id:
            return
        if task_id == parent_task_id:
            raise ValueError("A task cannot be moved beneath itself")
        if parent_task_id in self.repo.descendant_ids(task_id):
            raise ValueError(
                "A task cannot be moved beneath itself or its descendants"
            )
        moved_ids = {task_id, *self.repo.descendant_ids(task_id)}
        ancestor_ids = {parent_task_id}
        ancestor = self.repo.get(parent_task_id)
        while ancestor.parent_task_id is not None:
            ancestor_ids.add(ancestor.parent_task_id)
            ancestor = self.repo.get(ancestor.parent_task_id)
        dependency_adjacency = self._dependency_adjacency()
        for ancestor_id in ancestor_ids:
            for moved_id in moved_ids:
                if self._reachable(
                    ancestor_id,
                    moved_id,
                    dependency_adjacency,
                ) or self._reachable(
                    moved_id,
                    ancestor_id,
                    dependency_adjacency,
                ):
                    raise ValueError(
                        "An ancestor and its subtask cannot have a dependency relationship"
                    )
        adjacency = self._combined_adjacency()
        if self._reachable(task_id, parent_task_id, adjacency):
            raise ValueError(
                "That hierarchy change conflicts with existing dependencies"
            )

    def _dependency_adjacency(self) -> dict[int, set[int]]:
        adjacency: dict[int, set[int]] = {}
        for dependent_id, prerequisite_id in self.dependencies.dependency_pairs():
            adjacency.setdefault(dependent_id, set()).add(prerequisite_id)
        return adjacency

    @staticmethod
    def _validate_values(
        values: dict,
        *,
        task_type: str,
        require_title: bool,
    ) -> None:
        title = values.get("title")
        if require_title and (not isinstance(title, str) or not title.strip()):
            raise TaskValidationError("Title is required.")
        if title is not None and len(title.strip()) > TITLE_MAX_LENGTH:
            raise TaskValidationError(
                f"Title must be {TITLE_MAX_LENGTH} characters or fewer."
            )

        description = values.get("description", "")
        if not isinstance(description, str):
            raise TaskValidationError("Description must be text.")
        if len(description) > DESCRIPTION_MAX_LENGTH:
            raise TaskValidationError(
                f"Description must be {DESCRIPTION_MAX_LENGTH:,} characters or fewer."
            )

        completion_criterion = values.get("completion_criterion", "")
        if not isinstance(completion_criterion, str):
            raise TaskValidationError("Completion criterion must be text.")
        if len(completion_criterion) > DESCRIPTION_MAX_LENGTH:
            raise TaskValidationError(
                "Completion criterion must be "
                f"{DESCRIPTION_MAX_LENGTH:,} characters or fewer."
            )

        priority = values.get("priority", "Medium")
        if priority not in VALID_PRIORITIES:
            raise TaskValidationError("Priority must be High, Medium, or Low.")
        status = values.get("status", "Open")
        if status not in VALID_STATUSES:
            raise TaskValidationError(
                "Status must be Open, In Progress, Blocked, or Completed."
            )

        estimate = values.get("estimated_hours")
        if estimate is None:
            return
        if isinstance(estimate, bool):
            raise TaskValidationError("Estimated hours must be a number.")
        try:
            estimate_decimal = Decimal(str(estimate))
        except (InvalidOperation, ValueError):
            raise TaskValidationError("Estimated hours must be a number.") from None
        if not estimate_decimal.is_finite() or estimate_decimal <= 0:
            raise TaskValidationError("Estimated hours must be greater than zero.")
        if estimate_decimal * 4 != (estimate_decimal * 4).to_integral_value():
            raise TaskValidationError(
                "Estimated hours must use quarter-hour increments."
            )
        maximum = (
            EPIC_ESTIMATE_MAX_HOURS
            if task_type == "epic"
            else STANDARD_ESTIMATE_MAX_HOURS
        )
        if estimate_decimal > maximum:
            label = "Epic" if task_type == "epic" else "Standard task"
            raise TaskValidationError(
                f"{label} estimates cannot exceed {maximum:g} hours."
            )

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
