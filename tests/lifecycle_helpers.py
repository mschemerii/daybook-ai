"""Explicit recorded-work setup for tests whose subject is reopening/hierarchy."""
from datetime import date
from src.models.entities import TimeEntry
from src.repositories.time_entry_repository import TimeEntryRepository


def record_time(service, task_id):
    TimeEntryRepository(service.repo.db).create(TimeEntry(None, task_id, date.today(), 1, 'Test work'))


def recorded_task(service, **values):
    values.pop('status', None)
    task = service.create_task(**values)
    record_time(service, task.id)
    return service.complete_task(task.id)


def recorded_subtask(service, parent_id, **values):
    values.pop('status', None)
    task = service.add_subtask(parent_id, **values)
    record_time(service, task.id)
    return service.complete_task(task.id)
