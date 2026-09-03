from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from src.runtime.preferences import (
    VALID_APPEARANCES,
    load_appearance_preference,
    save_appearance_preference,
)


_DARK_STYLESHEET = """
QWidget {
    background: #0f1524;
    color: #eef2f8;
    font-size: 13px;
}
QMainWindow, QStatusBar { background: #0f1524; }
QLabel { background: transparent; }
QFrame#sidebar {
    background: #111a2d;
    border-right: 1px solid #283450;
}
QLabel#brand { font-size: 20px; font-weight: 700; }
QLabel#brandSubtle { color: #9ba8be; font-size: 11px; }
QLabel#pageTitle { font-size: 24px; font-weight: 700; }
QLabel#pageSubtitle, QLabel#mutedText { color: #aeb8c9; }
QListWidget#navigation {
    background: transparent;
    border: 0;
    outline: 0;
}
QListWidget#navigation::item {
    padding: 10px 12px;
    margin: 2px 0;
    border-radius: 6px;
}
QListWidget#navigation::item:selected {
    background: #24304d;
    color: #ffffff;
}
QFrame#metricCard, QFrame#contentCard {
    background: #182237;
    border: 1px solid #2d3a57;
    border-radius: 10px;
}
QLabel#metricLabel { color: #aeb8c9; font-size: 11px; }
QLabel#metricValue { font-size: 22px; font-weight: 700; }
QComboBox {
    background: #182237;
    border: 1px solid #3b4968;
    border-radius: 6px;
    padding: 6px 9px;
    min-height: 24px;
}
QComboBox QAbstractItemView { background: #182237; selection-background-color: #24304d; }
QStatusBar { border-top: 1px solid #283450; color: #aeb8c9; }
"""

_LIGHT_STYLESHEET = """
QWidget {
    background: #f4f6fa;
    color: #1d2633;
    font-size: 13px;
}
QMainWindow, QStatusBar { background: #f4f6fa; }
QLabel { background: transparent; }
QFrame#sidebar {
    background: #ffffff;
    border-right: 1px solid #d7dde7;
}
QLabel#brand { font-size: 20px; font-weight: 700; }
QLabel#brandSubtle { color: #667085; font-size: 11px; }
QLabel#pageTitle { font-size: 24px; font-weight: 700; }
QLabel#pageSubtitle, QLabel#mutedText { color: #667085; }
QListWidget#navigation {
    background: transparent;
    border: 0;
    outline: 0;
}
QListWidget#navigation::item {
    padding: 10px 12px;
    margin: 2px 0;
    border-radius: 6px;
}
QListWidget#navigation::item:selected {
    background: #e8ecf5;
    color: #111827;
}
QFrame#metricCard, QFrame#contentCard {
    background: #ffffff;
    border: 1px solid #d9dfe9;
    border-radius: 10px;
}
QLabel#metricLabel { color: #667085; font-size: 11px; }
QLabel#metricValue { font-size: 22px; font-weight: 700; }
QComboBox {
    background: #ffffff;
    border: 1px solid #c9d1dc;
    border-radius: 6px;
    padding: 6px 9px;
    min-height: 24px;
}
QComboBox QAbstractItemView { background: #ffffff; selection-background-color: #e8ecf5; }
QStatusBar { border-top: 1px solid #d7dde7; color: #667085; }
"""


def stylesheet_for(appearance: str) -> str:
    if appearance == "Dark":
        return _DARK_STYLESHEET
    if appearance == "Light":
        return _LIGHT_STYLESHEET
    raise ValueError(f"Unsupported appearance: {appearance!r}")


class AppearanceManager(QObject):
    """Own native appearance state and reuse Daybook's persisted preference."""

    appearance_changed = Signal(str)

    def __init__(self, application: QApplication, preference_path: Path):
        super().__init__()
        self.application = application
        self.preference_path = preference_path
        self._appearance = load_appearance_preference(preference_path)
        self._apply()

    @property
    def appearance(self) -> str:
        return self._appearance

    def set_appearance(self, appearance: str) -> None:
        if appearance not in VALID_APPEARANCES:
            raise ValueError(f"Unsupported appearance: {appearance!r}")
        if appearance == self._appearance:
            return
        try:
            save_appearance_preference(self.preference_path, appearance)
        except OSError:
            # The runtime switch remains usable even when the preference path
            # is temporarily read-only. A later successful change can persist.
            pass
        self._appearance = appearance
        self._apply()
        self.appearance_changed.emit(appearance)

    def _apply(self) -> None:
        self.application.setStyleSheet(stylesheet_for(self._appearance))
