from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    application = QApplication.instance()
    created = application is None
    if application is None:
        application = QApplication(["daybook-desktop-tests"])
    yield application
    application.processEvents()
    if created:
        application.quit()
