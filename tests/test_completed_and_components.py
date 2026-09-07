from __future__ import annotations

from tests.lifecycle_helpers import recorded_task, recorded_subtask, record_time

import ast
from pathlib import Path

from src.models.entities import Task


def test_completed_tasks_can_be_reopened(task_repo, task_service):
    created = recorded_task(task_service, title="Finished")
    completed = task_service.completed()
    assert [task.id for task in completed] == [created.id]

    reopened = task_service.reopen_task(created.id)
    assert reopened.status == "Open"
    assert task_service.completed() == []


def test_task_card_accepts_reopen_callback():
    source = Path("src/ui/components.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    task_card = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "task_card"
    )
    argument_names = [argument.arg for argument in task_card.args.args]
    assert "on_reopen" in argument_names
