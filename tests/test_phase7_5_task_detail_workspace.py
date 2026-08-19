from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = PROJECT_ROOT / "app.py"


def test_task_detail_uses_compact_workspace_tabs() -> None:
    app_source = APP_FILE.read_text(encoding="utf-8")

    assert '["Overview", "Epic tasks", "AI planning", "Time", "Structure"]' in app_source
    assert '["Overview", "AI planning", "Time", "Structure"]' in app_source
    assert "with overview_tab.form" in app_source
    assert "with ai_tab:" in app_source
    assert "with time_tab.form" in app_source
    assert "structure_tab.subheader" in app_source


def test_epic_and_ai_sections_are_routed_to_their_tabs() -> None:
    app_source = APP_FILE.read_text(encoding="utf-8")

    assert "with epic_tasks_tab:" in app_source
    assert "render_epic_tasks(selected_task, children)" in app_source
    assert "render_breakdown_planning(selected_task)" in app_source
