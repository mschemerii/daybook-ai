from __future__ import annotations

from datetime import date

from src.models.entities import TimeEntry
from src.repositories.task_repository import TaskRepository
from src.repositories.time_entry_repository import TimeEntryRepository

MAX_ENTRY_MINUTES = 12 * 60
MAX_DAILY_MINUTES = 24 * 60
TIME_ENTRY_NOTE_MAX_LENGTH = 4_000


class TimeEntryValidationError(ValueError):
    """Raised when a time entry violates deterministic recording rules."""


class TimeEntryService:
    def __init__(self, repo: TimeEntryRepository, tasks: TaskRepository):
        self.repo = repo
        self.tasks = tasks

    def create(
        self,
        task_id: int,
        *,
        work_date: date,
        minutes: int,
        note: str = "",
    ) -> TimeEntry:
        self.tasks.get(task_id)
        self._validate(work_date, minutes, note)
        self._validate_daily_total(work_date, minutes)
        return self.repo.create(TimeEntry(None, task_id, work_date, minutes, note))

    def update(
        self,
        entry_id: int,
        *,
        work_date: date,
        minutes: int,
        note: str = "",
    ) -> TimeEntry:
        current = self.repo.get(entry_id)
        self.tasks.get(current.task_id)
        self._validate(work_date, minutes, note)
        self._validate_daily_total(work_date, minutes, exclude_entry_id=entry_id)
        return self.repo.update(
            entry_id,
            TimeEntry(entry_id, current.task_id, work_date, minutes, note),
        )

    def delete(self, entry_id: int) -> None:
        self.repo.delete(entry_id)

    def list_for_task(self, task_id: int) -> list[TimeEntry]:
        self.tasks.get(task_id)
        return self.repo.list_for_task(task_id)

    def recorded_minutes(self, task_id: int, *, include_descendants: bool = False) -> int:
        self.tasks.get(task_id)
        task_ids = {task_id}
        if include_descendants:
            task_ids.update(self.tasks.descendant_ids(task_id))
        return self.repo.minutes_for_tasks(task_ids)

    @staticmethod
    def _validate(work_date: date, minutes: int, note: str) -> None:
        if not isinstance(work_date, date):
            raise TimeEntryValidationError("Work date is required.")
        if isinstance(minutes, bool) or not isinstance(minutes, int):
            raise TimeEntryValidationError("Duration must be a whole number of minutes.")
        if minutes < 1 or minutes > MAX_ENTRY_MINUTES:
            raise TimeEntryValidationError(
                "A time entry must be between 1 minute and 12 hours."
            )
        if not isinstance(note, str):
            raise TimeEntryValidationError("Time-entry note must be text.")
        if len(note) > TIME_ENTRY_NOTE_MAX_LENGTH:
            raise TimeEntryValidationError(
                f"Time-entry note must be {TIME_ENTRY_NOTE_MAX_LENGTH:,} characters or fewer."
            )

    def _validate_daily_total(
        self,
        work_date: date,
        minutes: int,
        *,
        exclude_entry_id: int | None = None,
    ) -> None:
        existing = self.repo.minutes_for_date(
            work_date,
            exclude_entry_id=exclude_entry_id,
        )
        if existing + minutes > MAX_DAILY_MINUTES:
            raise TimeEntryValidationError(
                "Recorded time cannot exceed 24 hours across all tasks on one day."
            )
