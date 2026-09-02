from __future__ import annotations

from collections import defaultdict
from datetime import date

from src.models.entities import Task, TimeEntry
from src.models.reporting import (
    ReportDataError,
    ReportRange,
    ReportResult,
    ReportTaskNode,
)
from src.repositories.reporting_repository import ReportingRepository
from src.utils.report_ranges import monthly_range


class ReportingService:
    def __init__(self, repo: ReportingRepository):
        self.repo = repo

    @staticmethod
    def _task_sort_key(task: Task) -> tuple[int, int]:
        order = task.subtask_order if task.subtask_order is not None else 2**31 - 1
        return order, int(task.id or 0)

    def build_report(
        self,
        report_range: ReportRange,
        *,
        today: date | None = None,
    ) -> ReportResult:
        snapshot = self.repo.load_snapshot(
            report_range.start_date,
            report_range.end_date,
        )
        tasks_by_id: dict[int, Task] = {}
        for task in snapshot.tasks:
            if task.id is None:
                raise ReportDataError("Persisted task is missing its stable ID.")
            task_id = int(task.id)
            if task_id in tasks_by_id:
                raise ReportDataError(f"Duplicate task ID {task_id} in reporting snapshot.")
            tasks_by_id[task_id] = task

        entries_by_task: dict[int, list[TimeEntry]] = defaultdict(list)
        seen_entry_ids: set[int] = set()
        for entry in snapshot.entries:
            if entry.id is None:
                raise ReportDataError("Persisted time entry is missing its stable ID.")
            entry_id = int(entry.id)
            if entry_id in seen_entry_ids:
                raise ReportDataError(f"Duplicate time-entry ID {entry_id} in reporting snapshot.")
            seen_entry_ids.add(entry_id)
            if entry.task_id not in tasks_by_id:
                raise ReportDataError(
                    f"Time entry {entry_id} references missing task {entry.task_id}."
                )
            if isinstance(entry.minutes, bool) or not isinstance(entry.minutes, int) or entry.minutes <= 0:
                raise ReportDataError(f"Time entry {entry_id} has invalid minutes.")
            entries_by_task[entry.task_id].append(entry)

        all_children: dict[int, list[Task]] = defaultdict(list)
        for task in snapshot.tasks:
            if task.parent_task_id is not None:
                if task.parent_task_id not in tasks_by_id:
                    raise ReportDataError(
                        f"Task {task.id} references missing parent {task.parent_task_id}."
                    )
                all_children[task.parent_task_id].append(task)
        for children in all_children.values():
            children.sort(key=self._task_sort_key)

        included_ids = set(entries_by_task)
        for task_id in tuple(included_ids):
            current_id = task_id
            visited: set[int] = set()
            while True:
                if current_id in visited:
                    raise ReportDataError("Task hierarchy contains a cycle.")
                visited.add(current_id)
                task = tasks_by_id[current_id]
                parent_id = task.parent_task_id
                if parent_id is None:
                    break
                included_ids.add(parent_id)
                current_id = parent_id

        included_children: dict[int, list[Task]] = defaultdict(list)
        for task_id in included_ids:
            task = tasks_by_id[task_id]
            if task.parent_task_id is not None and task.parent_task_id in included_ids:
                included_children[task.parent_task_id].append(task)
        for children in included_children.values():
            children.sort(key=self._task_sort_key)

        def build_node(task: Task, ancestry: frozenset[int]) -> ReportTaskNode:
            task_id = int(task.id)
            if task_id in ancestry:
                raise ReportDataError("Task hierarchy contains a cycle.")
            direct_entries = tuple(entries_by_task.get(task_id, ()))
            direct_minutes = sum(entry.minutes for entry in direct_entries)
            children = tuple(
                build_node(child, ancestry | {task_id})
                for child in included_children.get(task_id, ())
            )
            cumulative_minutes = direct_minutes + sum(
                child.cumulative_minutes for child in children
            )
            subtask_estimated_hours = float(
                sum(
                    child.estimated_hours or 0
                    for child in all_children.get(task_id, ())
                )
            )
            return ReportTaskNode(
                task=task,
                direct_minutes=direct_minutes,
                cumulative_minutes=cumulative_minutes,
                direct_entries=direct_entries,
                children=children,
                subtask_estimated_hours=subtask_estimated_hours,
            )

        root_tasks = [
            tasks_by_id[task_id]
            for task_id in included_ids
            if tasks_by_id[task_id].parent_task_id is None
        ]
        root_tasks.sort(key=lambda task: int(task.id))
        roots = tuple(build_node(task, frozenset()) for task in root_tasks)

        detailed_entries = tuple(
            sorted(snapshot.entries, key=lambda entry: (entry.work_date, int(entry.id)))
        )
        grand_total_minutes = sum(entry.minutes for entry in detailed_entries)

        current_tasks: tuple[Task, ...] = ()
        reference_today = today or date.today()
        current_month = monthly_range(reference_today)
        if (
            report_range.kind == "monthly"
            and report_range.start_date == current_month.start_date
            and report_range.end_date == current_month.end_date
        ):
            entry_minutes_by_task = {
                task_id: sum(entry.minutes for entry in entries)
                for task_id, entries in entries_by_task.items()
            }

            def hierarchy_minutes(task_id: int, ancestry: frozenset[int]) -> int:
                if task_id in ancestry:
                    raise ReportDataError("Task hierarchy contains a cycle.")
                total = entry_minutes_by_task.get(task_id, 0)
                for child in all_children.get(task_id, ()):
                    total += hierarchy_minutes(int(child.id), ancestry | {task_id})
                return total

            candidates = [
                task
                for task in snapshot.tasks
                if task.status != "Completed"
                and task.due_date is not None
                and report_range.start_date <= task.due_date <= report_range.end_date
                and hierarchy_minutes(int(task.id), frozenset()) == 0
            ]
            candidates.sort(key=lambda task: (task.due_date, int(task.id)))
            current_tasks = tuple(candidates)

        return ReportResult(
            report_range=report_range,
            roots=roots,
            detailed_entries=detailed_entries,
            current_tasks_in_progress=current_tasks,
            grand_total_minutes=grand_total_minutes,
        )
