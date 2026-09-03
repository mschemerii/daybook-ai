from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.agent.local_llm import LocalModelError
from src.desktop.dialogs import (
    ClarificationDialog,
    TaskDialog,
    TimeEntryDialog,
    configure_date_edit,
)
from src.desktop.widgets import ContentCard, MetricCard
from src.models.entities import JournalEntry, ProposalReview, Task
from src.models.reporting import ReportResult
from src.services.planning_service import Phase6ValidationError, Phase7ValidationError
from src.services.task_service import ReopenConfirmationRequired
from src.utils.report_ranges import (
    daily_range,
    monthly_range,
    quarterly_range,
    today_range,
    weekly_range,
    yearly_range,
)


def _format_minutes(minutes: int) -> str:
    hours, remainder = divmod(minutes, 60)
    return f"{hours}h {remainder}m" if hours else f"{remainder}m"


def _qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


def _date(value: QDate) -> date:
    return date(value.year(), value.month(), value.day())


def _error(parent: QWidget, title: str, exc: Exception) -> None:
    QMessageBox.warning(parent, title, str(exc))


class TodayView(QWidget):
    open_task_requested = Signal(int)
    journal_requested = Signal()

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self.services = services
        self.setObjectName("todayView")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 4, 0, 0)
        self.metrics = QGridLayout()
        self.layout.addLayout(self.metrics)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.focus_table = self._table("Recommended focus")
        right = QTabWidget()
        self.due_table = self._table("Due today")
        self.blocked_table = self._table("Blocked")
        self.completed_table = self._table("Completed")
        right.addTab(self.due_table, "Due today")
        right.addTab(self.blocked_table, "Blocked")
        right.addTab(self.completed_table, "Completed")
        splitter.addWidget(self.focus_table)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.layout.addWidget(splitter, 1)
        journal = QPushButton("Open today’s journal")
        journal.setProperty("primary", True)
        journal.clicked.connect(self.journal_requested)
        self.layout.addWidget(journal)
        self.refresh()

    def _table(self, name: str) -> QTableWidget:
        table = QTableWidget(0, 4)
        table.setObjectName(name.lower().replace(" ", "") + "Table")
        table.setHorizontalHeaderLabels(["Task", "Priority", "Due", "Status"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.cellDoubleClicked.connect(
            lambda row, _col, target=table: self._open_row(target, row)
        )
        return table

    def _open_row(self, table: QTableWidget, row: int) -> None:
        item = table.item(row, 0)
        if item is not None:
            self.open_task_requested.emit(int(item.data(Qt.ItemDataRole.UserRole)))

    @staticmethod
    def _fill(table: QTableWidget, tasks: list[Task]) -> None:
        table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            title = QTableWidgetItem(task.title)
            title.setData(Qt.ItemDataRole.UserRole, int(task.id))
            table.setItem(row, 0, title)
            table.setItem(row, 1, QTableWidgetItem(task.priority))
            table.setItem(
                row,
                2,
                QTableWidgetItem(task.due_date.isoformat() if task.due_date else "—"),
            )
            table.setItem(row, 3, QTableWidgetItem(task.status))

    def refresh(self) -> None:
        while self.metrics.count():
            item = self.metrics.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        open_tasks = self.services.tasks.list_all(False)
        due = self.services.task_service.due_today()
        blocked = self.services.task_service.blocked()
        completed = self.services.task_service.completed()
        journal = self.services.journals.get(date.today()) is not None
        today_minutes = self.services.time_entries.minutes_for_date(date.today())
        specs = (
            ("Open tasks", len(open_tasks)),
            ("Due today", len(due)),
            ("Blocked", len(blocked)),
            ("Time today", _format_minutes(today_minutes)),
            ("Journal", "Recorded" if journal else "Not recorded"),
        )
        for column, (label, value) in enumerate(specs):
            self.metrics.addWidget(MetricCard(label, str(value)), 0, column)
        self._fill(self.focus_table, self.services.task_service.focus_items())
        self._fill(self.due_table, due)
        self._fill(self.blocked_table, blocked)
        self._fill(self.completed_table, completed[:10])


class ProposalReviewDialog(QDialog):
    def __init__(self, services, review: ProposalReview, parent=None):
        super().__init__(parent)
        self.services = services
        self.proposal_id = review.proposal_id
        self.approved = False
        self.setWindowTitle("Review AI decomposition proposal")
        self.resize(1050, 600)
        layout = QVBoxLayout(self)
        boundary = QLabel(
            "Untrusted local AI proposal — no task is created until you review and explicitly approve it."
        )
        boundary.setWordWrap(True)
        layout.addWidget(boundary)
        summary = QLabel(review.summary)
        summary.setWordWrap(True)
        layout.addWidget(summary)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "Use",
                "Title",
                "Description",
                "Hours",
                "Priority",
                "Status",
                "Due",
                "Definition of done",
                "Prerequisite keys",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table, 1)
        row_actions = QHBoxLayout()
        up = QPushButton("Move up")
        down = QPushButton("Move down")
        insert = QPushButton("Insert task")
        remove = QPushButton("Remove selected")
        up.clicked.connect(lambda: self._move(-1))
        down.clicked.connect(lambda: self._move(1))
        insert.clicked.connect(self._insert)
        remove.clicked.connect(self._remove)
        row_actions.addWidget(up)
        row_actions.addWidget(down)
        row_actions.addWidget(insert)
        row_actions.addWidget(remove)
        row_actions.addStretch(1)
        layout.addLayout(row_actions)
        buttons = QDialogButtonBox()
        approve = buttons.addButton(
            "Approve and create tasks", QDialogButtonBox.ButtonRole.AcceptRole
        )
        approve.setProperty("primary", True)
        reject = buttons.addButton(
            "Reject proposal", QDialogButtonBox.ButtonRole.DestructiveRole
        )
        cancel = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        approve.clicked.connect(self._approve)
        reject.clicked.connect(self._reject)
        cancel.clicked.connect(self.reject)
        layout.addWidget(buttons)
        self._load(review)

    def _load(self, review: ProposalReview) -> None:
        self.table.setRowCount(len(review.items))
        for row, item in enumerate(review.items):
            use = QTableWidgetItem()
            use.setCheckState(
                Qt.CheckState.Checked if item.selected else Qt.CheckState.Unchecked
            )
            use.setData(Qt.ItemDataRole.UserRole, item.item_key)
            self.table.setItem(row, 0, use)
            self.table.setItem(row, 1, QTableWidgetItem(item.title))
            self.table.setItem(row, 2, QTableWidgetItem(item.description))
            self.table.setItem(row, 3, QTableWidgetItem(f"{item.estimated_hours:g}"))
            self.table.setItem(row, 4, QTableWidgetItem(item.priority))
            self.table.setItem(row, 5, QTableWidgetItem(item.status))
            self.table.setItem(
                row,
                6,
                QTableWidgetItem(item.due_date.isoformat() if item.due_date else ""),
            )
            self.table.setItem(row, 7, QTableWidgetItem(item.completion_criterion))
            self.table.setItem(
                row, 8, QTableWidgetItem(", ".join(item.prerequisite_item_keys))
            )

    def _keys(self) -> list[str]:
        return [
            str(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))
            for row in range(self.table.rowCount())
        ]

    def _move(self, direction: int) -> None:
        row = self.table.currentRow()
        target = row + direction
        if row < 0 or target < 0 or target >= self.table.rowCount():
            return
        keys = self._keys()
        keys[row], keys[target] = keys[target], keys[row]
        review = self.services.planning_service.reorder_review_items(
            self.proposal_id, keys
        )
        self._load(review)
        self.table.selectRow(target)

    def _insert(self) -> None:
        dialog = TaskDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            values = dialog.values()
            review = self.services.planning_service.add_review_item(
                self.proposal_id,
                title=values["title"],
                description=values["description"],
                estimated_hours=values["estimated_hours"] or 0.25,
                priority=values["priority"],
                status=values["status"],
                completion_criterion=values["completion_criterion"],
                due_date=values["due_date"],
            )
            self._load(review)
            self.table.selectRow(self.table.rowCount() - 1)
        except (ValueError, KeyError, Phase7ValidationError) as exc:
            _error(self, "Review task was not inserted", exc)

    def _remove(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        key = str(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))
        try:
            review = self.services.planning_service.remove_review_item(
                self.proposal_id, key
            )
            self._load(review)
        except (ValueError, KeyError, Phase7ValidationError) as exc:
            _error(self, "Review task was not removed", exc)

    def _sync(self) -> None:
        service = self.services.planning_service
        review = service.get_review(self.proposal_id)
        by_key = {item.item_key: item for item in review.items}
        for row in range(self.table.rowCount()):
            key = str(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))
            selected = self.table.item(row, 0).checkState() == Qt.CheckState.Checked
            if by_key[key].selected != selected:
                service.set_review_item_selected(self.proposal_id, key, selected)
            due_text = self.table.item(row, 6).text().strip()
            changes = {
                "title": self.table.item(row, 1).text(),
                "description": self.table.item(row, 2).text(),
                "estimated_hours": float(self.table.item(row, 3).text()),
                "priority": self.table.item(row, 4).text(),
                "status": self.table.item(row, 5).text(),
                "due_date": date.fromisoformat(due_text) if due_text else None,
                "completion_criterion": self.table.item(row, 7).text(),
            }
            current = by_key[key]
            if any(getattr(current, name) != value for name, value in changes.items()):
                service.update_review_item(self.proposal_id, key, changes)
            prerequisites = [
                value.strip()
                for value in self.table.item(row, 8).text().split(",")
                if value.strip()
            ]
            if tuple(prerequisites) != current.prerequisite_item_keys:
                service.set_review_prerequisites(self.proposal_id, key, prerequisites)

    def _approve(self) -> None:
        try:
            self._sync()
            validation = self.services.planning_service.validate_review(
                self.proposal_id
            )
            warning = "\n".join(validation.warnings)
            text = "Create the selected reviewed tasks?"
            if warning:
                text += "\n\nWarnings:\n" + warning
            if (
                QMessageBox.question(self, "Approve proposal", text)
                != QMessageBox.StandardButton.Yes
            ):
                return
            self.services.planning_service.approve_review(self.proposal_id)
            self.approved = True
            self.accept()
        except (ValueError, KeyError, Phase7ValidationError) as exc:
            _error(self, "Proposal validation failed", exc)

    def _reject(self) -> None:
        if (
            QMessageBox.question(
                self, "Reject proposal", "Reject this draft without creating tasks?"
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.services.planning_service.reject_review(self.proposal_id)
            self.reject()


class TasksView(QWidget):
    changed = Signal()

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self.services = services
        self.selected_task_id: int | None = None
        self.setObjectName("tasksView")
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        create = QPushButton("Create task")
        create.setObjectName("createTaskButton")
        create.setProperty("primary", True)
        create.clicked.connect(self.create_task_dialog)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        self.show_completed = QCheckBox("Show completed")
        self.show_completed.toggled.connect(self.refresh)
        toolbar.addWidget(create)
        toolbar.addWidget(refresh)
        toolbar.addStretch(1)
        toolbar.addWidget(self.show_completed)
        layout.addLayout(toolbar)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setObjectName("taskTree")
        self.tree.setHeaderLabels(["Task", "Priority", "Due", "Status"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.currentItemChanged.connect(self._selection_changed)
        splitter.addWidget(self.tree)
        self.detail = QWidget()
        self.detail_layout = QVBoxLayout(self.detail)
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)
        self.refresh()

    def _tree_item(self, task: Task) -> QTreeWidgetItem:
        item = QTreeWidgetItem(
            [
                task.title,
                task.priority,
                task.due_date.isoformat() if task.due_date else "—",
                task.status,
            ]
        )
        item.setData(0, Qt.ItemDataRole.UserRole, int(task.id))
        if self.services.task_service.is_blocked(int(task.id)):
            item.setForeground(0, QBrush(QColor("#c75b39")))
        for child in self.services.tasks.list_subtasks(int(task.id)):
            if self.show_completed.isChecked() or child.status != "Completed":
                item.addChild(self._tree_item(child))
        return item

    def refresh(self) -> None:
        selected = self.selected_task_id
        self.tree.clear()
        for task in self.services.tasks.list_roots(
            include_completed=self.show_completed.isChecked()
        ):
            self.tree.addTopLevelItem(self._tree_item(task))
        self.tree.expandAll()
        if selected is not None:
            matches = self.tree.findItems(
                "*", Qt.MatchFlag.MatchWildcard | Qt.MatchFlag.MatchRecursive, 0
            )
            for item in matches:
                if item.data(0, Qt.ItemDataRole.UserRole) == selected:
                    self.tree.setCurrentItem(item)
                    break
            else:
                self.selected_task_id = None
                self._select_first_or_render_empty()
        else:
            self._select_first_or_render_empty()

    def _select_first_or_render_empty(self) -> None:
        first = self.tree.topLevelItem(0)
        if first is not None:
            self.tree.setCurrentItem(first)
            return
        self._render_empty()

    def open_task(self, task_id: int) -> None:
        self.selected_task_id = task_id
        self.show_completed.setChecked(
            True
            if self.services.tasks.get(task_id).status == "Completed"
            else self.show_completed.isChecked()
        )
        self.refresh()

    def _clear_detail(self) -> None:
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _render_empty(self) -> None:
        self._clear_detail()
        self.detail_layout.addWidget(
            ContentCard(
                "Tasks",
                "Create a task to begin, or select an existing task to edit it, record time, manage dependencies, and use bounded planning tools.",
            )
        )
        create = QPushButton("Create your first task")
        create.setProperty("primary", True)
        create.clicked.connect(self.create_task_dialog)
        self.detail_layout.addWidget(create)
        self.detail_layout.addStretch(1)

    def _selection_changed(self, current, _previous) -> None:
        if current is None:
            self.selected_task_id = None
            self._render_empty()
            return
        self.selected_task_id = int(current.data(0, Qt.ItemDataRole.UserRole))
        self._render_detail()

    def create_task(self, values: dict) -> Task:
        created = self.services.task_service.create_task(**values)
        self.selected_task_id = int(created.id)
        self.changed.emit()
        self.refresh()
        return created

    def create_task_dialog(self) -> None:
        dialog = TaskDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.create_task(dialog.values())
        except (ValueError, KeyError) as exc:
            _error(self, "Task was not created", exc)

    def update_selected(self, values: dict) -> Task:
        task = self.services.task_service.update_task(
            int(self.selected_task_id), values
        )
        self.changed.emit()
        self.refresh()
        return task

    def _edit(self) -> None:
        task = self.services.tasks.get(int(self.selected_task_id))
        dialog = TaskDialog(self, task=task)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.update_selected(dialog.values())
        except (ValueError, KeyError) as exc:
            _error(self, "Task was not updated", exc)

    def _complete(self) -> None:
        try:
            self.services.task_service.complete_task(int(self.selected_task_id))
            self.changed.emit()
            self.refresh()
        except (ValueError, KeyError) as exc:
            _error(self, "Task cannot be completed", exc)

    def _reopen(self) -> None:
        try:
            self.services.task_service.reopen_task(int(self.selected_task_id))
        except ReopenConfirmationRequired as exc:
            if (
                QMessageBox.question(
                    self,
                    "Reopen affected tasks",
                    f"{exc}\n\nReopen the task and affected dependents?",
                )
                != QMessageBox.StandardButton.Yes
            ):
                return
            self.services.task_service.reopen_task(
                int(self.selected_task_id), confirm_dependency_cascade=True
            )
        except (ValueError, KeyError) as exc:
            _error(self, "Task cannot be reopened", exc)
            return
        self.changed.emit()
        self.refresh()

    def _delete(self) -> None:
        try:
            preview = self.services.task_service.deletion_preview(
                int(self.selected_task_id)
            )
            details = [
                f"Delete ‘{preview.task.title}’? This follows Daybook’s governed deletion behavior."
            ]
            if preview.preserved_tasks:
                details.append(
                    f"{len(preview.preserved_tasks)} timed descendant(s) will be preserved as standalone tasks."
                )
            if preview.deleted_tasks:
                details.append(
                    f"{len(preview.deleted_tasks)} untimed descendant(s) will also be deleted."
                )
            if preview.deletes_recorded_time:
                details.append("Recorded time on this task will be deleted.")
            if (
                QMessageBox.question(self, "Delete task", "\n\n".join(details))
                != QMessageBox.StandardButton.Yes
            ):
                return
            self.services.task_service.delete_task(
                int(self.selected_task_id), confirmed=True
            )
            self.selected_task_id = None
            self.changed.emit()
            self.refresh()
        except (ValueError, KeyError, PermissionError) as exc:
            _error(self, "Task was not deleted", exc)

    def _render_detail(self) -> None:
        self._clear_detail()
        try:
            task = self.services.tasks.get(int(self.selected_task_id))
        except KeyError:
            self._render_empty()
            return
        title = QLabel(task.title)
        title.setObjectName("taskDetailTitle")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.detail_layout.addWidget(title)
        actions = QHBoxLayout()
        edit = QPushButton("Edit")
        edit.clicked.connect(self._edit)
        state = QPushButton("Reopen" if task.status == "Completed" else "Complete")
        state.clicked.connect(
            self._reopen if task.status == "Completed" else self._complete
        )
        delete = QPushButton("Delete")
        delete.clicked.connect(self._delete)
        for button in (edit, state, delete):
            actions.addWidget(button)
        actions.addStretch(1)
        self.detail_layout.addLayout(actions)
        tabs = QTabWidget()
        tabs.addTab(self._overview_tab(task), "Overview")
        tabs.addTab(self._time_tab(task), "Time")
        tabs.addTab(self._structure_tab(task), "Structure")
        tabs.addTab(self._planning_tab(task), "AI planning")
        self.detail_layout.addWidget(tabs, 1)

    def _overview_tab(self, task: Task) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        fields = (
            ("Status", task.status),
            ("Priority", task.priority),
            ("Due date", task.due_date.isoformat() if task.due_date else "—"),
            (
                "Estimate",
                f"{task.estimated_hours:g}h"
                if task.estimated_hours is not None
                else "—",
            ),
            ("Type", task.task_type.title()),
            ("Description", task.description or "—"),
            ("Definition of done", task.completion_criterion or "—"),
            ("Notes", task.notes or "—"),
        )
        for label, value in fields:
            widget = QLabel(f"<b>{label}</b><br>{value}")
            widget.setWordWrap(True)
            widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(widget)
        if task.task_type == "epic":
            children = self.services.tasks.list_subtasks(int(task.id))
            recorded = self.services.time_entry_service.recorded_minutes(
                int(task.id), include_descendants=True
            )
            layout.addWidget(
                QLabel(
                    f"<b>Epic progress</b><br>{sum(c.status == 'Completed' for c in children)} of {len(children)} tasks complete · {_format_minutes(recorded)} cumulative"
                )
            )
        layout.addStretch(1)
        return page

    def _time_tab(self, task: Task) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        total = self.services.time_entry_service.recorded_minutes(
            int(task.id), include_descendants=task.task_type == "epic"
        )
        label = "Cumulative epic time" if task.task_type == "epic" else "Recorded time"
        total_label = QLabel(f"<b>{label}: {_format_minutes(total)}</b>")
        total_label.setObjectName("recordedTimeTotal")
        layout.addWidget(total_label)
        if task.task_type == "epic":
            layout.addWidget(
                QLabel(
                    "Time is entered on tasks and subtasks. Epics display cumulative descendant time."
                )
            )
        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["Date", "Duration", "Note"])
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        entries = self.services.time_entry_service.list_for_task(int(task.id))
        table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            first = QTableWidgetItem(entry.work_date.isoformat())
            first.setData(Qt.ItemDataRole.UserRole, int(entry.id))
            table.setItem(row, 0, first)
            table.setItem(row, 1, QTableWidgetItem(_format_minutes(entry.minutes)))
            table.setItem(row, 2, QTableWidgetItem(entry.note))
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(table, 1)
        buttons = QHBoxLayout()
        add = QPushButton("Add entry")
        add.setProperty("primary", True)
        edit = QPushButton("Edit entry")
        delete = QPushButton("Delete entry")
        add.setEnabled(task.task_type != "epic")
        add.clicked.connect(lambda: self._add_time(task))
        edit.clicked.connect(lambda: self._edit_time(task, table))
        delete.clicked.connect(lambda: self._delete_time(table))
        for button in (add, edit, delete):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return page

    def add_time(self, task_id: int, values: dict):
        entry = self.services.time_entry_service.create(task_id, **values)
        self.changed.emit()
        self._render_detail()
        return entry

    def _add_time(self, task: Task) -> None:
        dialog = TimeEntryDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.add_time(int(task.id), dialog.values())
            except (ValueError, KeyError) as exc:
                _error(self, "Time was not recorded", exc)

    def _selected_entry_id(self, table: QTableWidget) -> int | None:
        row = table.currentRow()
        return (
            int(table.item(row, 0).data(Qt.ItemDataRole.UserRole)) if row >= 0 else None
        )

    def _edit_time(self, task: Task, table: QTableWidget) -> None:
        entry_id = self._selected_entry_id(table)
        if entry_id is None:
            return
        entry = self.services.time_entries.get(entry_id)
        dialog = TimeEntryDialog(self, entry=entry)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.services.time_entry_service.update(entry_id, **dialog.values())
                self.changed.emit()
                self._render_detail()
            except (ValueError, KeyError) as exc:
                _error(self, "Time entry was not updated", exc)

    def _delete_time(self, table: QTableWidget) -> None:
        entry_id = self._selected_entry_id(table)
        if entry_id is None:
            return
        if (
            QMessageBox.question(
                self, "Delete time entry", "Delete the selected time entry?"
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.services.time_entry_service.delete(entry_id)
            self.changed.emit()
            self._render_detail()

    def _structure_tab(self, task: Task) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        parent_row = QHBoxLayout()
        parent_combo = QComboBox()
        parent_combo.addItem("Standalone task", None)
        for candidate in self.services.tasks.list_all(True):
            if candidate.id != task.id:
                parent_combo.addItem(candidate.title, int(candidate.id))
        parent_index = parent_combo.findData(task.parent_task_id)
        parent_combo.setCurrentIndex(max(0, parent_index))
        update_parent = QPushButton("Update parent")
        update_parent.clicked.connect(
            lambda: self._update_parent(task, parent_combo.currentData())
        )
        parent_row.addWidget(QLabel("Parent"))
        parent_row.addWidget(parent_combo, 1)
        parent_row.addWidget(update_parent)
        layout.addLayout(parent_row)
        children = self.services.tasks.list_subtasks(int(task.id))
        child_list = QListWidget()
        for child in children:
            item = QListWidgetItem(
                f"{(child.subtask_order or 0) + 1}. {child.title} · {child.status}"
            )
            item.setData(Qt.ItemDataRole.UserRole, int(child.id))
            child_list.addItem(item)
        layout.addWidget(QLabel("Ordered tasks"))
        layout.addWidget(child_list)
        row = QHBoxLayout()
        add = QPushButton("Add task")
        add.setProperty("primary", True)
        up = QPushButton("Move up")
        down = QPushButton("Move down")
        add.clicked.connect(lambda: self._add_subtask(task))
        up.clicked.connect(lambda: self._move_subtask(child_list, -1))
        down.clicked.connect(lambda: self._move_subtask(child_list, 1))
        for button in (add, up, down):
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        prerequisites = self.services.task_service.prerequisites(int(task.id))
        dependents = self.services.task_service.dependents(int(task.id))
        layout.addWidget(
            QLabel(
                "<b>Prerequisites</b><br>"
                + (", ".join(item.title for item in prerequisites) or "None")
            )
        )
        dep_row = QHBoxLayout()
        self._dependency_combo = QComboBox()
        candidates = [
            item for item in self.services.tasks.list_all(True) if item.id != task.id
        ]
        for candidate in candidates:
            self._dependency_combo.addItem(candidate.title, int(candidate.id))
        add_dep = QPushButton("Add prerequisite")
        remove_dep = QPushButton("Remove selected prerequisite")
        add_dep.clicked.connect(
            lambda: self._add_dependency(task, self._dependency_combo)
        )
        remove_dep.clicked.connect(lambda: self._remove_dependency(task, prerequisites))
        dep_row.addWidget(self._dependency_combo, 1)
        dep_row.addWidget(add_dep)
        dep_row.addWidget(remove_dep)
        layout.addLayout(dep_row)
        layout.addWidget(
            QLabel(
                "<b>Dependent tasks</b><br>"
                + (", ".join(item.title for item in dependents) or "None")
            )
        )
        layout.addStretch(1)
        return page

    def _update_parent(self, task: Task, parent_id: int | None) -> None:
        try:
            if parent_id is None and task.parent_task_id is not None:
                self.services.task_service.remove_subtask(int(task.id))
            elif parent_id is not None and parent_id != task.parent_task_id:
                self.services.task_service.reassign_subtask(
                    int(task.id), int(parent_id)
                )
            else:
                return
            self.changed.emit()
            self.refresh()
        except (ValueError, KeyError) as exc:
            _error(self, "Parent was not updated", exc)

    def _add_subtask(self, parent: Task) -> None:
        dialog = TaskDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            values = dialog.values()
            values.pop("status", None)
            self.services.task_service.add_subtask(int(parent.id), **values)
            self.changed.emit()
            self.refresh()
        except (ValueError, KeyError) as exc:
            _error(self, "Task was not added", exc)

    def _move_subtask(self, widget: QListWidget, direction: int) -> None:
        item = widget.currentItem()
        if item is None:
            return
        try:
            self.services.task_service.move_subtask(
                int(item.data(Qt.ItemDataRole.UserRole)), direction
            )
            self.changed.emit()
            self.refresh()
        except (ValueError, KeyError) as exc:
            _error(self, "Task was not moved", exc)

    def _add_dependency(self, task: Task, combo: QComboBox) -> None:
        if combo.currentIndex() < 0:
            return
        try:
            offer = self.services.task_service.add_dependency(
                int(task.id), int(combo.currentData())
            )
            if offer and offer.kind == "create_epic":
                answer = QMessageBox.question(
                    self,
                    "Related work",
                    "Dependency added. Convert these two standalone tasks into an ordered epic?",
                )
                if answer == QMessageBox.StandardButton.Yes:
                    title, accepted = QInputDialog.getText(
                        self,
                        "Create epic",
                        "Epic title",
                        text=offer.suggested_epic_name or "Related work",
                    )
                    if accepted:
                        self.services.task_service.convert_dependency_pair_to_epic(
                            offer.dependent_task_id,
                            offer.prerequisite_task_id,
                            title,
                        )
            elif offer and offer.kind == "append_to_epic":
                answer = QMessageBox.question(
                    self,
                    "Related epic",
                    "Dependency added. Add the dependent task to the prerequisite epic?",
                )
                if answer == QMessageBox.StandardButton.Yes:
                    self.services.task_service.append_dependent_to_epic(
                        offer.dependent_task_id,
                        offer.prerequisite_task_id,
                    )
            else:
                QMessageBox.information(self, "Dependency", "Dependency added.")
            self.changed.emit()
            self.refresh()
        except (ValueError, KeyError) as exc:
            _error(self, "Dependency was not added", exc)

    def _remove_dependency(self, task: Task, prerequisites: list[Task]) -> None:
        if not prerequisites:
            return
        choices = {item.title: int(item.id) for item in prerequisites}
        chooser = QComboBox()
        chooser.addItems(list(choices))
        dialog = QDialog(self)
        dialog.setWindowTitle("Remove prerequisite")
        layout = QVBoxLayout(dialog)
        layout.addWidget(chooser)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.services.task_service.remove_dependency(
                int(task.id), choices[chooser.currentText()]
            )
            self.changed.emit()
            self.refresh()

    def _planning_tab(self, task: Task) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        position = self._focus_position(task)
        facts = (
            self.services.task_service.ranking_facts(task, position)
            if position is not None
            else None
        )
        deterministic = QLabel(
            "<b>Application-rule explanation</b><br>"
            + (
                facts.deterministic_explanation
                if facts is not None
                else "This completed or blocked task is not in the current unblocked focus order."
            )
        )
        deterministic.setWordWrap(True)
        layout.addWidget(deterministic)
        output = QPlainTextEdit()
        output.setObjectName("planningOutput")
        output.setReadOnly(True)
        output.setPlaceholderText(
            "AI output is labeled untrusted and falls back to deterministic facts if unavailable."
        )
        layout.addWidget(output, 1)
        buttons = QHBoxLayout()
        explain = QPushButton("Explain with local AI")
        explain.setEnabled(position is not None)
        decompose = QPushButton("Propose breakdown")
        explain.clicked.connect(lambda: self._explain(task, output, position))
        decompose.clicked.connect(lambda: self._decompose(task, output))
        buttons.addWidget(explain)
        buttons.addWidget(decompose)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        boundary = QLabel(
            "Rules determine. AI explains and proposes. You review and approve every AI-originated task write."
        )
        boundary.setObjectName("mutedText")
        boundary.setWordWrap(True)
        layout.addWidget(boundary)
        return page

    def _focus_position(self, task: Task) -> int | None:
        focus = self.services.task_service.focus_items(
            limit=len(self.services.tasks.list_all(False))
        )
        return next(
            (index for index, item in enumerate(focus, start=1) if item.id == task.id),
            None,
        )

    def _explain(
        self, task: Task, output: QPlainTextEdit, position: int | None = None
    ) -> None:
        position = position or self._focus_position(task)
        if position is None:
            output.setPlainText(
                "No AI explanation was requested because this task is not in the current unblocked focus order."
            )
            return
        facts = self.services.task_service.ranking_facts(task, position)
        result = self.services.planning_service.explain_with_ai(facts)
        label = (
            "Untrusted local AI explanation"
            if result.used_ai
            else "Deterministic fallback"
        )
        output.setPlainText(
            f"{label}\n\n{result.text}"
            + (f"\n\n{result.message}" if result.message else "")
        )

    def _decompose(self, task: Task, output: QPlainTextEdit) -> None:
        try:
            answers = self.services.planning.get_clarification_answers(int(task.id))
            readiness = self.services.planning_service.readiness(task, answers)
            if not readiness.ready:
                dialog = ClarificationDialog(readiness.questions, answers, self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                answers.update(dialog.answers())
                self.services.planning.save_clarification_answers(int(task.id), answers)
                readiness = self.services.planning_service.readiness(task, answers)
                if not readiness.ready:
                    raise Phase6ValidationError(
                        "Complete every requested clarification before asking the model."
                    )
            result = self.services.planning_service.request_decomposition(task, answers)
            review = self.services.planning_service.get_review(
                result.proposal.proposal_id
            )
            dialog = ProposalReviewDialog(self.services, review, self)
            dialog.exec()
            output.setPlainText(
                "Proposal approved and tasks created."
                if dialog.approved
                else "Proposal closed or left as a draft. No task state was silently changed."
            )
            if dialog.approved:
                self.changed.emit()
                self.refresh()
        except (
            LocalModelError,
            ValueError,
            KeyError,
            Phase6ValidationError,
            Phase7ValidationError,
        ) as exc:
            output.setPlainText(
                "The AI-generated proposal failed validation before review. "
                "No task state changed, and deterministic features remain usable."
                f"\n\n{exc}"
            )


class JournalView(QWidget):
    changed = Signal()

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self.services = services
        self.setObjectName("journalView")
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        top = QHBoxLayout()
        self.date_edit = QDateEdit(_qdate(date.today()))
        configure_date_edit(self.date_edit)
        self.date_edit.dateChanged.connect(self.load)
        today = QPushButton("Today")
        today.clicked.connect(lambda: self.date_edit.setDate(_qdate(date.today())))
        date_label = QLabel("Journal date")
        date_label.setObjectName("fieldLabel")
        top.addWidget(date_label)
        top.addWidget(self.date_edit)
        top.addWidget(today)
        top.addStretch(1)
        layout.addLayout(top)

        entry_card = QFrame()
        entry_card.setObjectName("contentCard")
        entry_layout = QVBoxLayout(entry_card)
        entry_layout.setContentsMargins(18, 16, 18, 16)
        entry_title = QLabel("Document your day")
        entry_title.setObjectName("sectionTitle")
        entry_hint = QLabel(
            "Click inside any field below to begin writing. Save when the entry is complete."
        )
        entry_hint.setObjectName("mutedText")
        entry_layout.addWidget(entry_title)
        entry_layout.addWidget(entry_hint)
        form = QGridLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        self.editors = {}
        fields = (
            ("completed_today", "Completed today", 0, 0, 1),
            ("in_progress", "In progress", 0, 1, 1),
            ("blocked_waiting", "Blocked or waiting", 1, 0, 1),
            ("plan_tomorrow", "Plan for tomorrow", 1, 1, 1),
            ("reflections", "Notes and reflections", 2, 0, 2),
        )
        for key, label, row, column, column_span in fields:
            field = QWidget()
            field_layout = QVBoxLayout(field)
            field_layout.setContentsMargins(0, 0, 0, 0)
            field_layout.setSpacing(5)
            field_label = QLabel(label)
            field_label.setObjectName("fieldLabel")
            editor = QPlainTextEdit()
            editor.setObjectName(key + "Edit")
            editor.setAccessibleName(label)
            editor.setPlaceholderText(f"Enter {label.lower()}…")
            editor.setFixedHeight(78 if key != "reflections" else 88)
            self.editors[key] = editor
            field_layout.addWidget(field_label)
            field_layout.addWidget(editor)
            form.addWidget(field, row, column, 1, column_span)
        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 1)
        entry_layout.addLayout(form)
        save = QPushButton("Save journal entry")
        save.setObjectName("saveJournalButton")
        save.setProperty("primary", True)
        save.setAccessibleName("Save journal entry")
        save.clicked.connect(self.save)
        entry_layout.addWidget(save)
        layout.addWidget(entry_card)

        history_title = QLabel("Previous entries")
        history_title.setObjectName("sectionTitle")
        layout.addWidget(history_title)
        self.history = QListWidget()
        self.history.itemDoubleClicked.connect(
            lambda item: self.date_edit.setDate(
                _qdate(date.fromisoformat(str(item.data(Qt.ItemDataRole.UserRole))))
            )
        )
        layout.addWidget(self.history, 1)
        self.load()

    @property
    def selected_date(self) -> date:
        return _date(self.date_edit.date())

    def load(self, *_args) -> None:
        entry = self.services.journals.get(self.selected_date) or JournalEntry(
            self.selected_date
        )
        for key, editor in self.editors.items():
            editor.setPlainText(getattr(entry, key))
        self.history.clear()
        for recent in self.services.journals.list_recent(10):
            item = QListWidgetItem(
                f"{recent.entry_date.isoformat()} · {recent.completed_today[:70] or 'No completed-work note'}"
            )
            item.setData(Qt.ItemDataRole.UserRole, recent.entry_date.isoformat())
            self.history.addItem(item)

    def save_entry(self, entry: JournalEntry) -> JournalEntry:
        saved = self.services.journals.upsert(entry)
        self.changed.emit()
        self.load()
        return saved

    def save(self) -> None:
        values = {key: editor.toPlainText() for key, editor in self.editors.items()}
        self.save_entry(JournalEntry(self.selected_date, **values))


class ReportsView(QWidget):
    def __init__(self, services, parent=None):
        super().__init__(parent)
        self.services = services
        self.report: ReportResult | None = None
        self.setObjectName("reportsView")
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.period = QComboBox()
        self.period.addItems(
            ["Today", "Daily", "Weekly", "Monthly", "Quarterly", "Yearly"]
        )
        self.period.setCurrentText("Monthly")
        self.selected = QDateEdit(_qdate(date.today().replace(day=1)))
        configure_date_edit(self.selected)
        self.fiscal = QCheckBox("Fiscal quarter/year")
        self.fiscal_month = QSpinBox()
        self.fiscal_month.setRange(1, 12)
        self.fiscal_month.setValue(
            self.services.reporting_settings.get_fiscal_start_month()
        )
        self.fiscal_month.setPrefix("Fiscal start month: ")
        build = QPushButton("Build report")
        build.setObjectName("buildReportButton")
        build.setProperty("primary", True)
        build.clicked.connect(self.refresh)
        for widget in (
            self.period,
            self.selected,
            self.fiscal,
            self.fiscal_month,
            build,
        ):
            controls.addWidget(widget)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.summary = QLabel()
        self.summary.setObjectName("reportSummary")
        layout.addWidget(self.summary)
        self.table = QTreeWidget()
        self.table.setHeaderLabels(["Task", "Estimate", "Subtask estimate", "Recorded"])
        self.table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        exports = QHBoxLayout()
        pdf = QPushButton("Export summary PDF")
        detail = QPushButton("Export detailed PDF")
        csv = QPushButton("Export CSV ZIP")
        pdf.clicked.connect(lambda: self._export("summary.pdf"))
        detail.clicked.connect(lambda: self._export("detailed.pdf"))
        csv.clicked.connect(lambda: self._export("report.zip"))
        for button in (pdf, detail, csv):
            exports.addWidget(button)
        exports.addStretch(1)
        layout.addLayout(exports)
        self.refresh()

    def report_range(self):
        selected = _date(self.selected.date())
        kind = self.period.currentText()
        if kind == "Today":
            return today_range(date.today())
        if kind == "Daily":
            return daily_range(selected)
        if kind == "Weekly":
            return weekly_range(selected)
        if kind == "Monthly":
            return monthly_range(selected)
        if kind == "Quarterly":
            return quarterly_range(
                selected,
                fiscal=self.fiscal.isChecked(),
                fiscal_start_month=self.fiscal_month.value(),
            )
        return yearly_range(
            selected,
            fiscal=self.fiscal.isChecked(),
            fiscal_start_month=self.fiscal_month.value(),
        )

    def refresh(self) -> None:
        self.services.reporting_settings.set_fiscal_start_month(
            self.fiscal_month.value()
        )
        self.report = self.services.reporting_service.build_report(self.report_range())
        self.summary.setText(
            f"<b>{self.report.report_range.label}</b> · Total recorded: {_format_minutes(self.report.grand_total_minutes)}"
        )
        self.table.clear()

        def add(node, parent=None):
            task = node.task
            item = QTreeWidgetItem(
                [
                    task.title + (" (Epic)" if task.task_type == "epic" else ""),
                    f"{task.estimated_hours:g}h"
                    if task.estimated_hours is not None
                    else "—",
                    f"{node.subtask_estimated_hours:g}h"
                    if task.task_type == "epic"
                    else "—",
                    _format_minutes(node.display_minutes),
                ]
            )
            (parent.addChild(item) if parent else self.table.addTopLevelItem(item))
            for child in node.children:
                add(child, item)

        for root in self.report.roots:
            add(root)
        self.table.expandAll()

    def _export(self, suffix: str) -> None:
        if self.report is None:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export report", str(Path.home() / f"daybook-{suffix}")
        )
        if not filename:
            return
        if suffix == "summary.pdf":
            payload = self.services.report_export_service.export_summary_pdf(
                self.report
            )
        elif suffix == "detailed.pdf":
            payload = self.services.report_export_service.export_detailed_pdf(
                self.report
            )
        else:
            payload = self.services.report_export_service.export_csv_zip(self.report)
        Path(filename).write_bytes(payload)


class AssistantView(QWidget):
    def __init__(self, services, ai_status: str, parent=None):
        super().__init__(parent)
        self.services = services
        self.setObjectName("assistantView")
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        self.status = QLabel()
        self.status.setObjectName("mutedText")
        layout.addWidget(self.status)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        conversation = QFrame()
        conversation.setObjectName("contentCard")
        conversation_layout = QVBoxLayout(conversation)
        conversation_layout.setContentsMargins(18, 16, 18, 16)
        conversation_title = QLabel("Ask the local assistant")
        conversation_title.setObjectName("sectionTitle")
        conversation_hint = QLabel(
            "Type a request below. Daybook sends only the local records you explicitly allow."
        )
        conversation_hint.setObjectName("mutedText")
        conversation_hint.setWordWrap(True)
        conversation_layout.addWidget(conversation_title)
        conversation_layout.addWidget(conversation_hint)
        request_label = QLabel("Your request")
        request_label.setObjectName("fieldLabel")
        conversation_layout.addWidget(request_label)
        self.request = QPlainTextEdit()
        self.request.setObjectName("assistantRequest")
        self.request.setAccessibleName("Your request to Daybook AI")
        self.request.setPlaceholderText("For example: What should I focus on today?")
        self.request.setFixedHeight(105)
        conversation_layout.addWidget(self.request)
        row = QHBoxLayout()
        send = QPushButton("Send request")
        send.setObjectName("assistantSendButton")
        send.setProperty("primary", True)
        health = QPushButton("Check local AI")
        send.clicked.connect(self.send)
        health.clicked.connect(self.check_health)
        row.addWidget(send)
        row.addWidget(health)
        row.addStretch(1)
        conversation_layout.addLayout(row)
        response_label = QLabel("Assistant response")
        response_label.setObjectName("fieldLabel")
        conversation_layout.addWidget(response_label)
        self.output = QPlainTextEdit()
        self.output.setObjectName("assistantOutput")
        self.output.setAccessibleName("Assistant response")
        self.output.setReadOnly(True)
        self.output.setPlaceholderText(
            "The local assistant’s response will appear here."
        )
        conversation_layout.addWidget(self.output, 1)
        self.provenance = QLabel("No local records consulted.")
        self.provenance.setObjectName("mutedText")
        self.provenance.setWordWrap(True)
        conversation_layout.addWidget(self.provenance)

        controls = QWidget()
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        access = QGroupBox("Local data access for this request")
        access_layout = QVBoxLayout(access)
        self.include_tasks = QCheckBox("Allow selected task fields")
        self.include_journal = QCheckBox("Allow recent journal fields")
        self.retain = QCheckBox("Save assistant memory")
        for item in (self.include_tasks, self.include_journal, self.retain):
            access_layout.addWidget(item)
        access_hint = QLabel(
            "Access is off by default and applies only to this request."
        )
        access_hint.setObjectName("mutedText")
        access_hint.setWordWrap(True)
        access_layout.insertWidget(0, access_hint)
        controls_layout.addWidget(access)
        history = QTabWidget()
        memory_page = QWidget()
        memory_layout = QVBoxLayout(memory_page)
        self.memory_list = QListWidget()
        delete_memory = QPushButton("Delete selected memory")
        delete_memory.clicked.connect(self.delete_memory)
        memory_layout.addWidget(self.memory_list)
        memory_layout.addWidget(delete_memory)
        audit_page = QWidget()
        audit_layout = QVBoxLayout(audit_page)
        self.audit_list = QListWidget()
        delete_audit = QPushButton("Delete selected audit record")
        clear_audit = QPushButton("Delete all audit history")
        delete_audit.clicked.connect(self.delete_audit)
        clear_audit.clicked.connect(self.clear_audit)
        audit_layout.addWidget(self.audit_list)
        audit_layout.addWidget(delete_audit)
        audit_layout.addWidget(clear_audit)
        history.addTab(memory_page, "Memory")
        history.addTab(audit_page, "Audit")
        controls_layout.addWidget(history, 1)
        splitter.addWidget(conversation)
        splitter.addWidget(controls)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        self.set_status(ai_status)
        self.refresh_history()

    def set_status(self, status: str) -> None:
        self.status.setText(
            f"Local AI: {status}. Tasks, journals, and reports remain available independently."
        )

    def check_health(self) -> None:
        ok, message = self.services.model.healthcheck(False)
        self.set_status("Ready" if ok else "Unavailable")
        self.output.setPlainText(message)

    def send(self) -> None:
        request = self.request.toPlainText().strip()
        if not request:
            return
        records, provenance = self.services.context_service.build(
            self.include_tasks.isChecked(), self.include_journal.isChecked()
        )
        try:
            answer = self.services.model.chat(request, records)
            self.output.setPlainText("Local AI interpretation\n\n" + answer)
            self.provenance.setText(
                "Records consulted: " + json.dumps(provenance, ensure_ascii=False)
            )
            self.services.governance.add_audit(request, provenance, answer)
            if self.retain.isChecked():
                self.services.governance.create_memory(
                    f"Request: {request}\nResponse: {answer}"
                )
            self.refresh_history()
        except LocalModelError as exc:
            self.output.setPlainText(
                f"Local AI unavailable. Deterministic features remain usable.\n\n{exc}"
            )
            self.set_status("Unavailable")

    def refresh_history(self) -> None:
        self.memory_list.clear()
        for memory in self.services.governance.list_memories():
            item = QListWidgetItem(memory["content"][:160])
            item.setData(Qt.ItemDataRole.UserRole, int(memory["id"]))
            self.memory_list.addItem(item)
        self.audit_list.clear()
        for audit in self.services.governance.list_audit():
            item = QListWidgetItem(
                f"{audit['created_at']} · {audit['user_request'][:100]}"
            )
            item.setData(Qt.ItemDataRole.UserRole, int(audit["id"]))
            self.audit_list.addItem(item)

    def delete_memory(self) -> None:
        item = self.memory_list.currentItem()
        if item is not None:
            self.services.governance.delete_memory(
                int(item.data(Qt.ItemDataRole.UserRole))
            )
            self.refresh_history()

    def delete_audit(self) -> None:
        item = self.audit_list.currentItem()
        if item is not None:
            self.services.governance.delete_audit(
                int(item.data(Qt.ItemDataRole.UserRole))
            )
            self.refresh_history()

    def clear_audit(self) -> None:
        if (
            QMessageBox.question(
                self, "Delete audit history", "Delete all assistant audit history?"
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.services.governance.clear_audit()
            self.refresh_history()


def ethical_ai_view(parent=None) -> QWidget:
    view = QWidget(parent)
    layout = QVBoxLayout(view)
    layout.addWidget(
        ContentCard(
            "Rules determine. AI explains. AI proposes. Humans approve.",
            "Daybook keeps task state, priority, validation, persistence, and reporting in deterministic application services. The local model can interpret or propose, never silently decide or write.",
        )
    )
    principles = (
        (
            "Human autonomy",
            "AI-originated task writes require visible review and explicit approval.",
        ),
        (
            "Privacy and minimization",
            "SQLite and model context remain local; only fields the user selects are provided to the model.",
        ),
        (
            "Transparency",
            "Application-rule results and untrusted AI interpretation are labeled separately.",
        ),
        (
            "Accountability",
            "Assistant requests, provenance, responses, and approvals are auditable and user-controlled.",
        ),
        (
            "No surveillance",
            "No productivity scoring, automatic time tracking, keystroke monitoring, or peer ranking.",
        ),
        (
            "NIST AI RMF alignment",
            "Conceptual course-project alignment through human governance, explicit local data flows, deterministic measurement, and visible risk controls; this is not a certification.",
        ),
    )
    grid = QGridLayout()
    for index, (title, body) in enumerate(principles):
        grid.addWidget(ContentCard(title, body), index // 2, index % 2)
    layout.addLayout(grid)

    policy_card = QFrame()
    policy_card.setObjectName("contentCard")
    policy_layout = QVBoxLayout(policy_card)
    policy_layout.setContentsMargins(18, 16, 18, 16)
    policy_title = QLabel("Interactive action policy")
    policy_title.setObjectName("sectionTitle")
    policy_hint = QLabel(
        "Select an example to see whether Daybook allows it, requires human confirmation, or prohibits it."
    )
    policy_hint.setObjectName("mutedText")
    policy_hint.setWordWrap(True)
    examples = {
        "Summarize selected local tasks": ("Allowed", "allowed"),
        "Propose creating a task": ("Requires confirmation", "confirmation"),
        "Complete a task from an AI suggestion": (
            "Requires confirmation",
            "confirmation",
        ),
        "Delete source information automatically": ("Prohibited", "prohibited"),
        "Send an email or message": ("Prohibited", "prohibited"),
        "Monitor keystrokes or application usage": ("Prohibited", "prohibited"),
    }
    choice = QComboBox()
    choice.setObjectName("ethicalActionCombo")
    choice.setAccessibleName("Example AI action")
    choice.addItems(list(examples))
    result = QLabel()
    result.setObjectName("ethicalActionResult")

    def update_policy(selected: str) -> None:
        label, category = examples[selected]
        result.setText(label)
        result.setProperty("policyStatus", category)
        result.style().unpolish(result)
        result.style().polish(result)

    choice.currentTextChanged.connect(update_policy)
    update_policy(choice.currentText())
    policy_layout.addWidget(policy_title)
    policy_layout.addWidget(policy_hint)
    policy_layout.addWidget(choice)
    policy_layout.addWidget(result)
    layout.addWidget(policy_card)
    layout.addStretch(1)
    return view


def about_view(parent=None) -> QWidget:
    view = QWidget(parent)
    layout = QVBoxLayout(view)
    layout.addWidget(
        ContentCard(
            "About Daybook AI",
            "A local-first personal task manager, daily journal, deterministic reporting system, and bounded local AI assistant designed and coded by Michael Schemer.",
        )
    )
    layout.addWidget(
        ContentCard(
            "Architecture",
            "PySide6 desktop presentation calls the existing Python repositories and services directly. SQLite remains authoritative, llama.cpp remains local and optional, and Streamlit remains available as the Phase 9B fallback interface.",
        )
    )
    layout.addStretch(1)
    return view
