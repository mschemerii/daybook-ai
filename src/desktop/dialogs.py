from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.models.entities import Task, TimeEntry
from src.services.task_service import (
    DESCRIPTION_MAX_LENGTH,
    STANDARD_ESTIMATE_MAX_HOURS,
    TITLE_MAX_LENGTH,
)


def _qdate(value: date | None = None) -> QDate:
    selected = value or date.today()
    return QDate(selected.year, selected.month, selected.day)


def _date(value: QDate) -> date:
    return date(value.year(), value.month(), value.day())


def configure_date_edit(editor: QDateEdit) -> None:
    """Give every popup calendar clear, conventional month navigation."""
    editor.setCalendarPopup(True)
    editor.setDisplayFormat("MM-dd-yyyy")
    calendar: QCalendarWidget = editor.calendarWidget()
    calendar.setGridVisible(True)
    for name, symbol, accessible_name in (
        ("qt_calendar_prevmonth", "‹", "Previous month"),
        ("qt_calendar_nextmonth", "›", "Next month"),
    ):
        button = calendar.findChild(QToolButton, name)
        if button is not None:
            button.setIcon(QIcon())
            button.setText(symbol)
            button.setAccessibleName(accessible_name)
            button.setToolTip(accessible_name)
    month_button = calendar.findChild(QToolButton, "qt_calendar_monthbutton")
    if month_button is not None:
        month_button.setMenu(None)
        month_button.setPopupMode(QToolButton.ToolButtonPopupMode.DelayedPopup)
        month_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        month_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)


class TaskDialog(QDialog):
    """Native create/edit form; the service remains the validation authority."""

    def __init__(self, parent: QWidget | None = None, *, task: Task | None = None):
        super().__init__(parent)
        self.task = task
        self.setWindowTitle("Edit task" if task else "Create task")
        self.resize(720, 660)
        self.setMinimumSize(640, 600)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(10)

        self.title_edit = QLineEdit(task.title if task else "")
        self.title_edit.setObjectName("taskTitleEdit")
        self.title_edit.setMaxLength(TITLE_MAX_LENGTH)
        self.title_edit.setAccessibleName("Task title")
        self.title_edit.setPlaceholderText("Enter a short task title")
        self.description_edit = QPlainTextEdit(task.description if task else "")
        self.description_edit.setObjectName("taskDescriptionEdit")
        self.description_edit.setMaximumBlockCount(1000)
        self.description_edit.setMaximumHeight(105)
        self.description_edit.setPlaceholderText(
            "Describe the work and intended outcome"
        )
        self.priority_combo = QComboBox()
        self.priority_combo.addItems(["High", "Medium", "Low"])
        self.priority_combo.setCurrentText(task.priority if task else "Medium")
        self.status_combo = QComboBox()
        self.status_combo.addItems(["Open", "In Progress", "Blocked", "Completed"])
        self.status_combo.setCurrentText(task.status if task else "Open")
        if task and task.status == "Completed":
            self.status_combo.setEnabled(False)

        self.has_due = QCheckBox("Set due date")
        self.has_due.setChecked(bool(task and task.due_date))
        self.due_edit = QDateEdit(_qdate(task.due_date if task else None))
        configure_date_edit(self.due_edit)
        self.due_edit.setEnabled(self.has_due.isChecked())
        self.has_due.toggled.connect(self.due_edit.setEnabled)

        self.has_estimate = QCheckBox("Set estimate")
        self.has_estimate.setChecked(bool(task and task.estimated_hours is not None))
        self.estimate_spin = QDoubleSpinBox()
        self.estimate_spin.setRange(0.25, float(STANDARD_ESTIMATE_MAX_HOURS))
        self.estimate_spin.setSingleStep(0.25)
        self.estimate_spin.setDecimals(2)
        self.estimate_spin.setSuffix(" hours")
        self.estimate_spin.setToolTip(
            "Multiweek estimates are allowed. Estimates of 40 hours or more prompt a breakdown reminder."
        )
        self.estimate_spin.setValue(
            task.estimated_hours if task and task.estimated_hours else 0.25
        )
        self.estimate_spin.setEnabled(self.has_estimate.isChecked())
        self.has_estimate.toggled.connect(self.estimate_spin.setEnabled)

        self.notes_edit = QPlainTextEdit(task.notes if task else "")
        self.done_edit = QPlainTextEdit(task.completion_criterion if task else "")
        self.notes_edit.setPlaceholderText(
            "Add planning notes, constraints, or context"
        )
        self.done_edit.setPlaceholderText("Describe what must be true for completion")
        for editor in (self.description_edit, self.notes_edit, self.done_edit):
            editor.setTabChangesFocus(True)

        def field_label(text: str) -> QLabel:
            label = QLabel(text)
            label.setObjectName("fieldLabel")
            return label

        layout.addWidget(field_label("Title (50 characters maximum)"))
        layout.addWidget(self.title_edit)
        layout.addWidget(field_label("Description"))
        layout.addWidget(self.description_edit)

        details = QGridLayout()
        details.setHorizontalSpacing(16)
        details.setVerticalSpacing(6)
        details.setColumnStretch(0, 1)
        details.setColumnStretch(1, 1)
        details.addWidget(field_label("Priority"), 0, 0)
        details.addWidget(field_label("Status"), 0, 1)
        details.addWidget(self.priority_combo, 1, 0)
        details.addWidget(self.status_combo, 1, 1)
        details.addWidget(self.has_due, 2, 0)
        details.addWidget(self.has_estimate, 2, 1)
        details.addWidget(self.due_edit, 3, 0)
        details.addWidget(self.estimate_spin, 3, 1)
        details.addWidget(field_label("Notes"), 4, 0)
        details.addWidget(field_label("Definition of done"), 4, 1)
        details.addWidget(self.notes_edit, 5, 0)
        details.addWidget(self.done_edit, 5, 1)
        details.setRowStretch(5, 1)
        layout.addLayout(details, 1)
        note = QLabel(
            "Daybook validates titles, descriptions, status, estimates, hierarchy, and dependencies when saved."
        )
        note.setObjectName("mutedText")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setProperty(
            "primary", True
        )
        buttons.accepted.connect(self._accept_checked)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_checked(self) -> None:
        if len(self.description_edit.toPlainText()) > DESCRIPTION_MAX_LENGTH:
            QMessageBox.warning(
                self, "Invalid task", "Description must be 4,000 characters or fewer."
            )
            return
        if len(self.done_edit.toPlainText()) > DESCRIPTION_MAX_LENGTH:
            QMessageBox.warning(
                self,
                "Invalid task",
                "Definition of done must be 4,000 characters or fewer.",
            )
            return
        if self.has_estimate.isChecked() and self.estimate_spin.value() >= 40:
            answer = QMessageBox.question(
                self,
                "Large estimate",
                "This estimate is at least five workdays. Save it without breaking the work into smaller tasks?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.accept()

    def values(self) -> dict:
        return {
            "title": self.title_edit.text().strip(),
            "description": self.description_edit.toPlainText(),
            "priority": self.priority_combo.currentText(),
            "status": self.status_combo.currentText(),
            "due_date": _date(self.due_edit.date())
            if self.has_due.isChecked()
            else None,
            "estimated_hours": self.estimate_spin.value()
            if self.has_estimate.isChecked()
            else None,
            "notes": self.notes_edit.toPlainText(),
            "completion_criterion": self.done_edit.toPlainText(),
        }


class TimeEntryDialog(QDialog):
    def __init__(
        self, parent: QWidget | None = None, *, entry: TimeEntry | None = None
    ):
        super().__init__(parent)
        self.setWindowTitle("Edit time entry" if entry else "Add time entry")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.date_edit = QDateEdit(_qdate(entry.work_date if entry else None))
        configure_date_edit(self.date_edit)
        self.minutes_spin = QSpinBox()
        self.minutes_spin.setObjectName("timeMinutesSpin")
        self.minutes_spin.setRange(1, 720)
        self.minutes_spin.setValue(entry.minutes if entry else 30)
        self.note_edit = QPlainTextEdit(entry.note if entry else "")
        form.addRow("Work date", self.date_edit)
        form.addRow("Minutes (1–720)", self.minutes_spin)
        form.addRow("Note", self.note_edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setProperty(
            "primary", True
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "work_date": _date(self.date_edit.date()),
            "minutes": self.minutes_spin.value(),
            "note": self.note_edit.toPlainText(),
        }


class ClarificationDialog(QDialog):
    def __init__(
        self,
        questions: tuple[tuple[str, str], ...],
        existing: dict[str, str],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Planning clarification")
        self.resize(640, 480)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "The local model receives only these answers and the selected task fields. Complete the missing information before requesting a proposal."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.editors: dict[str, QPlainTextEdit] = {}
        for key, question in questions:
            editor = QPlainTextEdit(existing.get(key, ""))
            editor.setMaximumHeight(85)
            self.editors[key] = editor
            form.addRow(question, editor)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def answers(self) -> dict[str, str]:
        return {
            key: editor.toPlainText().strip()
            for key, editor in self.editors.items()
            if editor.toPlainText().strip()
        }
