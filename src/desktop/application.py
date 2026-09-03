from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from PySide6.QtWidgets import QApplication

from src.desktop.composition import (
    DesktopCompositionConfig,
    DesktopServices,
    build_desktop_services,
)
from src.desktop.main_window import MainWindow
from src.desktop.theme import AppearanceManager


@dataclass(slots=True)
class DesktopApplication:
    application: QApplication
    window: MainWindow
    services: DesktopServices
    appearance: AppearanceManager
    owns_application: bool


def _ensure_application(argv: Sequence[str] | None = None) -> tuple[QApplication, bool]:
    existing = QApplication.instance()
    if existing is not None:
        if not isinstance(existing, QApplication):
            raise RuntimeError("A non-GUI Qt application already exists in this process.")
        return existing, False

    application = QApplication(list(argv) if argv is not None else sys.argv[:1])
    application.setApplicationName("Daybook AI")
    application.setOrganizationName("Daybook AI")
    application.setQuitOnLastWindowClosed(True)
    return application, True


def build_desktop_application(
    project_root: Path,
    *,
    config: DesktopCompositionConfig | None = None,
    services: DesktopServices | None = None,
    argv: Sequence[str] | None = None,
) -> DesktopApplication:
    """Construct the native application without entering the Qt event loop."""
    resolved_config = config or DesktopCompositionConfig.from_environment(project_root)
    resolved_services = services or build_desktop_services(resolved_config)
    application, owns_application = _ensure_application(argv)
    appearance = AppearanceManager(application, resolved_config.preferences_path)
    window = MainWindow(resolved_services, appearance)
    return DesktopApplication(
        application=application,
        window=window,
        services=resolved_services,
        appearance=appearance,
        owns_application=owns_application,
    )


def run_desktop_application(project_root: Path) -> int:
    """Show the native Daybook window and run until the user closes it."""
    desktop = build_desktop_application(project_root)
    desktop.window.show()
    if not desktop.owns_application:
        return 0
    return int(desktop.application.exec())
