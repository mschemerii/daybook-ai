from __future__ import annotations

from datetime import date
from pathlib import Path

from src.desktop.composition import (
    DesktopCompositionConfig,
    build_desktop_services,
)


def test_desktop_composition_reaches_existing_services(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DAYBOOK_LLM_VERIFIED", "false")
    config = DesktopCompositionConfig(
        project_root=tmp_path,
        database_path=tmp_path / "daybook.db",
        preferences_path=tmp_path / ".daybook-preferences.json",
        seed_demo=False,
        model_base_url="http://127.0.0.1:8080/v1",
        model_name="auto",
        model_api_key="",
    )

    services = build_desktop_services(config)
    snapshot = services.shell_snapshot(today=date(2026, 9, 2))

    assert services.tasks.list_all() == []
    assert services.context_service.build(True, True) == ([], [])
    assert services.task_service.due_today(date(2026, 9, 2)) == []
    assert services.reporting_service.repo is services.reporting
    assert services.planning_service.model is services.model
    assert snapshot.open_tasks == 0
    assert snapshot.completed_tasks == 0
    assert snapshot.ai_status == "Unavailable"
    assert snapshot.database_name == "daybook.db"


def test_environment_composition_reuses_daybook_preference_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DAYBOOK_DB_PATH", "data/test.db")
    monkeypatch.setenv("DAYBOOK_PREFERENCES_PATH", ".daybook-preferences.json")
    monkeypatch.setenv("DAYBOOK_SEED_DEMO", "0")

    config = DesktopCompositionConfig.from_environment(tmp_path)

    assert config.database_path == (tmp_path / "data/test.db").resolve()
    assert config.preferences_path == (tmp_path / ".daybook-preferences.json").resolve()
    assert config.seed_demo is False
