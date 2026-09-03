from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox

from src.desktop.composition import ShellSnapshot
from src.desktop.main_window import MainWindow
from src.desktop.theme import AppearanceManager


@dataclass
class FakeServices:
    snapshot: ShellSnapshot
    calls: int = 0

    def shell_snapshot(self) -> ShellSnapshot:
        self.calls += 1
        return self.snapshot


def make_services(*, ai_status: str = "Ready") -> FakeServices:
    return FakeServices(
        ShellSnapshot(
            open_tasks=3,
            due_today=1,
            completed_tasks=2,
            journal_today=True,
            ai_status=ai_status,
            database_name="daybook.db",
        )
    )


def test_main_window_constructs_and_reaches_services(qapp, tmp_path: Path) -> None:
    services = make_services()
    appearance = AppearanceManager(qapp, tmp_path / "prefs.json")

    window = MainWindow(services, appearance)  # type: ignore[arg-type]

    assert services.calls == 1
    assert window.windowTitle() == "Daybook AI"
    assert window.current_destination == "today"
    assert window.navigation_keys == (
        "today",
        "tasks",
        "journal",
        "reports",
        "assistant",
        "ethical-ai",
        "about",
        "settings",
    )
    window.close()


def test_navigation_changes_workspace_without_rerun(qapp, tmp_path: Path) -> None:
    appearance = AppearanceManager(qapp, tmp_path / "prefs.json")
    window = MainWindow(make_services(), appearance)  # type: ignore[arg-type]
    first_stack_index = window.stack.currentIndex()

    window.navigate("reports")
    qapp.processEvents()

    assert window.current_destination == "reports"
    assert window.stack.currentIndex() != first_stack_index
    assert window.page_title.text() == "Reports"
    assert window.status_message.text() == "Viewing Reports"
    with pytest.raises(ValueError):
        window.navigate("missing")
    window.close()


def test_appearance_switch_persists_and_survives_restart(qapp, tmp_path: Path) -> None:
    preference_path = tmp_path / ".daybook-preferences.json"
    appearance = AppearanceManager(qapp, preference_path)
    assert appearance.appearance == "Light"

    appearance.set_appearance("Dark")

    assert appearance.appearance == "Dark"
    assert json.loads(preference_path.read_text(encoding="utf-8")) == {
        "appearance": "Dark"
    }
    restarted = AppearanceManager(qapp, preference_path)
    assert restarted.appearance == "Dark"
    assert "#0f1524" in qapp.styleSheet()


def test_settings_control_switches_appearance(qapp, tmp_path: Path) -> None:
    preference_path = tmp_path / "prefs.json"
    appearance = AppearanceManager(qapp, preference_path)
    window = MainWindow(make_services(), appearance)  # type: ignore[arg-type]
    window.navigate("settings")

    combo = window.findChild(QComboBox, "appearanceCombo")
    assert combo is not None
    combo.setCurrentText("Dark")
    qapp.processEvents()

    assert appearance.appearance == "Dark"
    assert preference_path.exists()
    window.close()


def test_model_unavailable_status_keeps_shell_usable(qapp, tmp_path: Path) -> None:
    appearance = AppearanceManager(qapp, tmp_path / "prefs.json")
    services = make_services(ai_status="Unavailable")
    window = MainWindow(services, appearance)  # type: ignore[arg-type]

    assert "deterministic features remain available" in window.ai_status.text()
    window.navigate("tasks")
    assert window.current_destination == "tasks"
    window.close()


def test_close_emits_lifecycle_signal(qapp, tmp_path: Path) -> None:
    appearance = AppearanceManager(qapp, tmp_path / "prefs.json")
    window = MainWindow(make_services(), appearance)  # type: ignore[arg-type]
    events: list[str] = []
    window.closing.connect(lambda: events.append("closing"))

    window.show()
    qapp.processEvents()
    window.close()
    qapp.processEvents()

    assert events == ["closing"]
    assert not window.isVisible()


def test_navigation_items_are_keyboard_focusable(qapp, tmp_path: Path) -> None:
    appearance = AppearanceManager(qapp, tmp_path / "prefs.json")
    window = MainWindow(make_services(), appearance)  # type: ignore[arg-type]

    assert window.navigation.focusPolicy() != Qt.FocusPolicy.NoFocus
    assert window.navigation.accessibleName() == "Daybook navigation"
    window.close()
