from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = PROJECT_ROOT / "app.py"


def test_phase7_5_bounded_task_views_are_present() -> None:
    app_source = APP_FILE.read_text(encoding="utf-8")

    assert 'def open_task_view(view: str)' in app_source
    assert '("Open tasks", len(open_tasks), "Open", "open")' in app_source
    assert '("Due today", len(due), "Due today", "due")' in app_source
    assert '("Blockers", len(blocked), "Blocked", "blocked")' in app_source
    assert '("Completed", len(completed), "Completed", "completed")' in app_source
    assert '["Overview", "Open", "Due today", "Blocked", "Completed"]' in app_source
    assert 'current_tasks = tasks.list_all(False)' in app_source
    assert 'current_tasks = task_service.due_today()' in app_source
    assert 'current_tasks = task_service.blocked()' in app_source
    assert 'current_tasks = task_service.completed()' in app_source
    assert 'Inside epic: {parent.title}' in app_source
    assert 'Local AI ready · {Path(loaded_model).name}' in app_source
