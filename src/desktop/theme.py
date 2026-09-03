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
QPushButton {
    background: #24304d;
    border: 1px solid #465778;
    border-radius: 6px;
    padding: 7px 13px;
    min-height: 22px;
    font-weight: 600;
}
QPushButton:hover { background: #314365; border-color: #63779f; }
QPushButton:pressed { background: #1c2740; }
QPushButton:disabled { color: #748097; background: #182237; border-color: #2d3a57; }
QPushButton[primary="true"] {
    background: #6d5ce7;
    border-color: #8172f2;
    color: #ffffff;
}
QPushButton[primary="true"]:hover { background: #7c6bf0; }
QLineEdit, QPlainTextEdit, QTextEdit, QDateEdit, QSpinBox, QDoubleSpinBox {
    background: #101827;
    border: 1px solid #465778;
    border-radius: 6px;
    padding: 7px;
    selection-background-color: #6d5ce7;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QDateEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus { border: 2px solid #8172f2; }
QTableWidget, QTreeWidget, QListWidget {
    background: #101827;
    alternate-background-color: #141e31;
    border: 1px solid #34425f;
    border-radius: 6px;
    gridline-color: #2d3a57;
    outline: 0;
}
QTableWidget::item, QTreeWidget::item, QListWidget::item {
    padding: 5px;
}
QTableWidget::item:selected, QTreeWidget::item:selected,
QListWidget::item:selected { background: #334a73; }
QHeaderView::section {
    background: #182237;
    border: 0;
    border-right: 1px solid #34425f;
    border-bottom: 1px solid #34425f;
    padding: 7px;
    font-weight: 600;
}
QTabWidget::pane { border: 1px solid #34425f; border-radius: 6px; top: -1px; }
QTabBar::tab {
    background: #182237;
    border: 1px solid #34425f;
    padding: 7px 14px;
    margin-right: 2px;
}
QTabBar::tab:selected { background: #334a73; border-color: #536b97; }
QGroupBox {
    border: 1px solid #34425f;
    border-radius: 8px;
    margin-top: 13px;
    padding-top: 10px;
    font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
QCheckBox { spacing: 7px; }
QCheckBox::indicator {
    width: 16px; height: 16px; background: #101827;
    border: 1px solid #596a8b; border-radius: 4px;
}
QCheckBox::indicator:checked { background: #6d5ce7; border-color: #8172f2; }
QLabel#sectionTitle { font-size: 16px; font-weight: 700; }
QLabel#fieldLabel { font-weight: 600; }
QLabel[policyStatus="allowed"] { color: #6dde9b; font-weight: 700; }
QLabel[policyStatus="confirmation"] { color: #f7c66b; font-weight: 700; }
QLabel[policyStatus="prohibited"] { color: #ff8585; font-weight: 700; }
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
QCalendarWidget QWidget#qt_calendar_navigationbar { background: #182237; }
QCalendarWidget QToolButton {
    background: #24304d;
    color: #ffffff;
    border: 1px solid #536587;
    border-radius: 5px;
    padding: 5px 10px;
    font-weight: 700;
}
QCalendarWidget QToolButton:hover { background: #314365; border-color: #8172f2; }
QCalendarWidget QToolButton#qt_calendar_prevmonth,
QCalendarWidget QToolButton#qt_calendar_nextmonth {
    min-width: 30px;
    font-size: 20px;
}
QCalendarWidget QToolButton#qt_calendar_monthbutton,
QCalendarWidget QToolButton#qt_calendar_yearbutton {
    background: transparent;
    border: 0;
}
QCalendarWidget QAbstractItemView {
    background: #101827;
    color: #eef2f8;
    selection-background-color: #6d5ce7;
    selection-color: #ffffff;
}
QCalendarWidget QSpinBox { background: #101827; color: #ffffff; }
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
QPushButton {
    background: #ffffff;
    border: 1px solid #aeb8c8;
    border-radius: 6px;
    padding: 7px 13px;
    min-height: 22px;
    font-weight: 600;
}
QPushButton:hover { background: #edf1f7; border-color: #7d8ba1; }
QPushButton:pressed { background: #e0e6ef; }
QPushButton:disabled { color: #98a2b3; background: #f1f3f7; border-color: #d7dde7; }
QPushButton[primary="true"] {
    background: #5b4bd5;
    border-color: #4f40c1;
    color: #ffffff;
}
QPushButton[primary="true"]:hover { background: #6858df; }
QLineEdit, QPlainTextEdit, QTextEdit, QDateEdit, QSpinBox, QDoubleSpinBox {
    background: #ffffff;
    border: 1px solid #aeb8c8;
    border-radius: 6px;
    padding: 7px;
    selection-background-color: #6757df;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QDateEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus { border: 2px solid #6757df; }
QTableWidget, QTreeWidget, QListWidget {
    background: #ffffff;
    alternate-background-color: #f6f8fb;
    border: 1px solid #cbd3df;
    border-radius: 6px;
    gridline-color: #d7dde7;
    outline: 0;
}
QTableWidget::item, QTreeWidget::item, QListWidget::item {
    padding: 5px;
}
QTableWidget::item:selected, QTreeWidget::item:selected,
QListWidget::item:selected { background: #dfe6f5; color: #111827; }
QHeaderView::section {
    background: #eef1f6;
    border: 0;
    border-right: 1px solid #cbd3df;
    border-bottom: 1px solid #cbd3df;
    padding: 7px;
    font-weight: 600;
}
QTabWidget::pane { border: 1px solid #cbd3df; border-radius: 6px; top: -1px; }
QTabBar::tab {
    background: #eef1f6;
    border: 1px solid #cbd3df;
    padding: 7px 14px;
    margin-right: 2px;
}
QTabBar::tab:selected { background: #dfe6f5; border-color: #9eabc0; }
QGroupBox {
    border: 1px solid #cbd3df;
    border-radius: 8px;
    margin-top: 13px;
    padding-top: 10px;
    font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
QCheckBox { spacing: 7px; }
QCheckBox::indicator {
    width: 16px; height: 16px; background: #ffffff;
    border: 1px solid #8d99aa; border-radius: 4px;
}
QCheckBox::indicator:checked { background: #5b4bd5; border-color: #4f40c1; }
QLabel#sectionTitle { font-size: 16px; font-weight: 700; }
QLabel#fieldLabel { font-weight: 600; }
QLabel[policyStatus="allowed"] { color: #087a46; font-weight: 700; }
QLabel[policyStatus="confirmation"] { color: #9a5c00; font-weight: 700; }
QLabel[policyStatus="prohibited"] { color: #b42318; font-weight: 700; }
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
QCalendarWidget QWidget#qt_calendar_navigationbar { background: #eef1f6; }
QCalendarWidget QToolButton {
    background: #ffffff;
    color: #1d2633;
    border: 1px solid #aeb8c8;
    border-radius: 5px;
    padding: 5px 10px;
    font-weight: 700;
}
QCalendarWidget QToolButton:hover { background: #edf1f7; border-color: #6757df; }
QCalendarWidget QToolButton#qt_calendar_prevmonth,
QCalendarWidget QToolButton#qt_calendar_nextmonth {
    min-width: 30px;
    font-size: 20px;
}
QCalendarWidget QToolButton#qt_calendar_monthbutton,
QCalendarWidget QToolButton#qt_calendar_yearbutton {
    background: transparent;
    border: 0;
}
QCalendarWidget QAbstractItemView {
    background: #ffffff;
    color: #1d2633;
    selection-background-color: #5b4bd5;
    selection-color: #ffffff;
}
QCalendarWidget QSpinBox { background: #ffffff; color: #1d2633; }
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
