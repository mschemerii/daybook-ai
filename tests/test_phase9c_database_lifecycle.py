from __future__ import annotations

import sqlite3
from pathlib import Path

from src.desktop.composition import DesktopCompositionConfig, build_desktop_services


def config_for(tmp_path: Path) -> DesktopCompositionConfig:
    return DesktopCompositionConfig(
        project_root=tmp_path,
        database_path=tmp_path / "daybook.db",
        preferences_path=tmp_path / "preferences.json",
        seed_demo=False,
        model_base_url="http://127.0.0.1:1/v1",
        model_name="auto",
        model_api_key="",
    )


def test_composition_restart_preserves_data_and_releases_database(tmp_path: Path) -> None:
    config = config_for(tmp_path)
    first = build_desktop_services(config)
    task = first.task_service.create_task(
        title="Persisted across restart",
        description="Lifecycle validation",
        priority="Medium",
        status="Open",
        due_date=None,
        estimated_hours=1.0,
        notes="",
        completion_criterion="Data survives a new composition.",
    )

    second = build_desktop_services(config)
    assert second.tasks.get(task.id).title == "Persisted across restart"

    connection = sqlite3.connect(config.database_path, timeout=0)
    try:
        connection.execute("BEGIN EXCLUSIVE")
        connection.execute("ROLLBACK")
    finally:
        connection.close()


def test_each_application_run_builds_one_independent_shared_graph(tmp_path: Path) -> None:
    config = config_for(tmp_path)
    first = build_desktop_services(config)
    second = build_desktop_services(config)

    assert first.tasks.db is first.database
    assert first.task_service.repo is first.tasks
    assert first.planning_service.model is first.model
    assert second.database is not first.database
    assert second.tasks is not first.tasks
