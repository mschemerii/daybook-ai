from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.models.entities import Task, TimeEntry


class ReportDataError(ValueError):
    """Raised when persisted reporting data cannot be interpreted safely."""


@dataclass(frozen=True, slots=True)
class ReportRange:
    kind: str
    start_date: date
    end_date: date
    label: str
    fiscal: bool = False

    def __post_init__(self) -> None:
        allowed_kinds = {
            "today",
            "daily",
            "weekly",
            "monthly",
            "quarterly",
            "yearly",
            "custom",
        }
        if self.kind not in allowed_kinds:
            raise ValueError(f"Unknown report range kind: {self.kind}")
        if not isinstance(self.start_date, date) or not isinstance(self.end_date, date):
            raise ValueError("Report range requires valid start and end dates.")
        if self.start_date > self.end_date:
            raise ValueError("Report range start date must be on or before end date.")


@dataclass(frozen=True, slots=True)
class ReportingSnapshot:
    tasks: tuple[Task, ...]
    entries: tuple[TimeEntry, ...]


@dataclass(frozen=True, slots=True)
class ReportTaskNode:
    task: Task
    direct_minutes: int
    cumulative_minutes: int
    direct_entries: tuple[TimeEntry, ...]
    children: tuple["ReportTaskNode", ...]
    subtask_estimated_hours: float

    @property
    def display_minutes(self) -> int:
        """Epics show cumulative hierarchy time; other tasks show direct time."""
        if self.task.task_type == "epic":
            return self.cumulative_minutes
        return self.direct_minutes


@dataclass(frozen=True, slots=True)
class ReportResult:
    report_range: ReportRange
    roots: tuple[ReportTaskNode, ...]
    detailed_entries: tuple[TimeEntry, ...]
    current_tasks_in_progress: tuple[Task, ...]
    grand_total_minutes: int

    @property
    def has_activity(self) -> bool:
        return bool(self.detailed_entries)

    def iter_nodes(self) -> tuple[ReportTaskNode, ...]:
        result: list[ReportTaskNode] = []

        def visit(node: ReportTaskNode) -> None:
            result.append(node)
            for child in node.children:
                visit(child)

        for root in self.roots:
            visit(root)
        return tuple(result)
