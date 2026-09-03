from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.desktop.application import build_desktop_application
from src.desktop.composition import DesktopCompositionConfig, ShellSnapshot


@dataclass
class FakeServices:
    calls: int = 0

    def shell_snapshot(self) -> ShellSnapshot:
        self.calls += 1
        return ShellSnapshot(
            open_tasks=1,
            due_today=0,
            completed_tasks=0,
            journal_today=False,
            ai_status="Not checked",
            database_name="test.db",
        )


def test_desktop_application_constructs_without_event_loop(qapp, tmp_path: Path) -> None:
    config = DesktopCompositionConfig(
        project_root=tmp_path,
        database_path=tmp_path / "test.db",
        preferences_path=tmp_path / ".daybook-preferences.json",
        seed_demo=False,
        model_base_url="http://127.0.0.1:8080/v1",
        model_name="auto",
        model_api_key="",
    )
    services = FakeServices()

    desktop = build_desktop_application(
        tmp_path,
        config=config,
        services=services,  # type: ignore[arg-type]
        argv=["daybook-test"],
    )

    assert desktop.application is qapp
    assert desktop.window.windowTitle() == "Daybook AI"
    assert desktop.window.current_destination == "today"
    assert services.calls == 1
    desktop.window.close()
