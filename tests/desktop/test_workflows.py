from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
)

from src.agent.local_llm import LocalModelError
from src.desktop.application import build_desktop_application
from src.desktop.composition import DesktopCompositionConfig, build_desktop_services
from src.desktop.dialogs import TaskDialog
from src.desktop.views import (
    AssistantView,
    JournalView,
    ReportsView,
    TasksView,
    TodayView,
    ProposalReviewDialog,
)
from src.models.entities import JournalEntry


def make_desktop(qapp, tmp_path: Path):
    config = DesktopCompositionConfig(
        project_root=tmp_path,
        database_path=tmp_path / "daybook.db",
        preferences_path=tmp_path / "preferences.json",
        seed_demo=False,
        model_base_url="http://127.0.0.1:1/v1",
        model_name="auto",
        model_api_key="",
    )
    services = build_desktop_services(config)
    return build_desktop_application(
        tmp_path,
        config=config,
        services=services,
        argv=["daybook-test"],
    )


def task_values(title: str, **overrides):
    values = {
        "title": title,
        "description": "Desktop workflow task",
        "priority": "Medium",
        "status": "Open",
        "due_date": None,
        "estimated_hours": 1.0,
        "notes": "",
        "completion_criterion": "The workflow is verified.",
    }
    values.update(overrides)
    return values


def test_real_desktop_constructs_every_workflow_once(qapp, tmp_path: Path) -> None:
    desktop = make_desktop(qapp, tmp_path)

    assert isinstance(desktop.window.today_view, TodayView)
    assert isinstance(desktop.window.tasks_view, TasksView)
    assert isinstance(desktop.window.journal_view, JournalView)
    assert isinstance(desktop.window.reports_view, ReportsView)
    assert isinstance(desktop.window.assistant_view, AssistantView)
    assert desktop.window.tasks_view.services is desktop.services
    assert (
        desktop.window.reports_view.services.reporting_service
        is desktop.services.reporting_service
    )
    desktop.window.close()


def test_dark_mode_exposes_clear_input_and_primary_action_affordances(
    qapp, tmp_path: Path
) -> None:
    desktop = make_desktop(qapp, tmp_path)
    desktop.appearance.set_appearance("Dark")
    stylesheet = qapp.styleSheet()

    assert 'QPushButton[primary="true"]' in stylesheet
    assert "QPlainTextEdit" in stylesheet
    assert "QTableWidget" in stylesheet

    journal = desktop.window.journal_view
    assert journal is not None
    save = journal.findChild(QPushButton, "saveJournalButton")
    assert save is not None
    assert save.property("primary") is True
    assert all(editor.placeholderText() for editor in journal.editors.values())
    assert all(editor.accessibleName() for editor in journal.editors.values())
    desktop.window.close()


def test_assistant_has_labeled_request_and_visible_primary_send_action(
    qapp, tmp_path: Path
) -> None:
    desktop = make_desktop(qapp, tmp_path)
    assistant = desktop.window.assistant_view
    assert assistant is not None

    send = assistant.findChild(QPushButton, "assistantSendButton")
    assert send is not None
    assert send.text() == "Send request"
    assert send.property("primary") is True
    assert assistant.request.accessibleName() == "Your request to Daybook AI"
    assert "For example" in assistant.request.placeholderText()
    desktop.window.close()


def test_ethical_ai_restores_interactive_action_policy(qapp, tmp_path: Path) -> None:
    desktop = make_desktop(qapp, tmp_path)
    desktop.window.navigate("ethical-ai")
    choice = desktop.window.findChild(QComboBox, "ethicalActionCombo")
    result = desktop.window.findChild(QLabel, "ethicalActionResult")

    assert choice is not None
    assert result is not None
    choice.setCurrentText("Send an email or message")
    qapp.processEvents()
    assert result.text() == "Prohibited"
    assert result.property("policyStatus") == "prohibited"
    choice.setCurrentText("Propose creating a task")
    qapp.processEvents()
    assert result.text() == "Requires confirmation"
    desktop.window.close()


def test_task_dialog_supports_multiweek_estimates_and_calendar_arrows(qapp) -> None:
    dialog = TaskDialog()

    assert dialog.minimumWidth() >= 640
    dialog.has_estimate.setChecked(True)
    assert dialog.estimate_spin.maximum() == 1000
    dialog.estimate_spin.setValue(120)
    assert dialog.values()["estimated_hours"] == 120

    dialog.has_due.setChecked(True)
    calendar = dialog.due_edit.calendarWidget()
    previous = calendar.findChild(QToolButton, "qt_calendar_prevmonth")
    following = calendar.findChild(QToolButton, "qt_calendar_nextmonth")
    month = calendar.findChild(QToolButton, "qt_calendar_monthbutton")
    assert previous is not None and previous.text() == "‹"
    assert following is not None and following.text() == "›"
    assert previous.isEnabled() and following.isEnabled()
    assert month is not None and month.menu() is None
    assert calendar.isGridVisible()
    dialog.close()


def test_task_create_edit_complete_and_reopen_through_native_view(
    qapp, tmp_path: Path
) -> None:
    desktop = make_desktop(qapp, tmp_path)
    view = desktop.window.tasks_view
    assert view is not None

    task = view.create_task(task_values("Native task", due_date=date.today()))
    assert desktop.services.tasks.get(task.id).title == "Native task"
    assert view.selected_task_id == task.id

    view.selected_task_id = None
    view.refresh()
    assert view.selected_task_id == task.id
    assert view.tree.currentItem() is not None

    updated = view.update_selected({"title": "Edited native task", "priority": "High"})
    assert updated.title == "Edited native task"
    desktop.services.task_service.complete_task(task.id)
    assert desktop.services.tasks.get(task.id).status == "Completed"
    desktop.services.task_service.reopen_task(task.id)
    assert desktop.services.tasks.get(task.id).status == "Open"
    desktop.window.close()


def test_dependency_and_epic_time_use_domain_services_and_cumulative_display(
    qapp, tmp_path: Path
) -> None:
    desktop = make_desktop(qapp, tmp_path)
    services = desktop.services
    parent = services.task_service.create_task(
        **task_values("Parent work", estimated_hours=4.0)
    )
    first = services.task_service.add_subtask(parent.id, **task_values("First step"))
    second = services.task_service.add_subtask(parent.id, **task_values("Second step"))
    services.task_service.add_dependency(second.id, first.id)
    services.time_entry_service.create(first.id, work_date=date.today(), minutes=45)
    services.time_entry_service.create(second.id, work_date=date.today(), minutes=30)

    assert services.task_service.blocking_prerequisites(second.id) == [
        services.tasks.get(first.id)
    ]
    assert (
        services.time_entry_service.recorded_minutes(
            parent.id, include_descendants=True
        )
        == 75
    )
    assert services.time_entry_service.list_for_task(parent.id) == []

    view = desktop.window.tasks_view
    assert view is not None
    view.open_task(parent.id)
    labels = [label.text() for label in view.detail.findChildren(QLabel)]
    assert any("1h 15m cumulative" in text for text in labels)
    desktop.window.close()


def test_journal_save_reload_and_today_status(qapp, tmp_path: Path) -> None:
    desktop = make_desktop(qapp, tmp_path)
    view = desktop.window.journal_view
    assert view is not None

    view.save_entry(
        JournalEntry(
            date.today(), completed_today="Saved natively", plan_tomorrow="Continue"
        )
    )
    view.load()

    assert view.editors["completed_today"].toPlainText() == "Saved natively"
    assert desktop.services.shell_snapshot().journal_today is True
    desktop.window.today_view.refresh()
    metric_text = [
        label.text() for label in desktop.window.today_view.findChildren(QLabel)
    ]
    assert "Recorded" in metric_text
    desktop.window.close()


def test_reports_preserve_sunday_week_and_epic_cumulative_time(
    qapp, tmp_path: Path
) -> None:
    desktop = make_desktop(qapp, tmp_path)
    services = desktop.services
    parent = services.task_service.create_task(**task_values("Report epic"))
    child = services.task_service.add_subtask(parent.id, **task_values("Report child"))
    services.time_entry_service.create(
        child.id, work_date=date(2026, 8, 30), minutes=90
    )
    view = desktop.window.reports_view
    assert view is not None
    view.period.setCurrentText("Weekly")
    view.selected.setDate(QDate(2026, 9, 3))
    view.refresh()

    assert view.report.report_range.start_date == date(2026, 8, 30)
    assert view.report.report_range.end_date == date(2026, 9, 5)
    assert view.report.roots[0].display_minutes == 90
    assert view.report.grand_total_minutes == 90
    desktop.window.close()


class UnavailableModel:
    def chat(self, request, records):
        raise LocalModelError("test model offline")

    def model_identity(self):
        raise LocalModelError("test model offline")


def test_assistant_unavailable_state_does_not_mutate_or_disable_tasks(
    qapp, tmp_path: Path
) -> None:
    desktop = make_desktop(qapp, tmp_path)
    task = desktop.services.task_service.create_task(**task_values("Still available"))
    view = desktop.window.assistant_view
    assert view is not None
    desktop.services.model = UnavailableModel()  # type: ignore[assignment]
    view.services = desktop.services
    view.request.setPlainText("Summarize")
    view.send()

    assert "Deterministic features remain usable" in view.output.toPlainText()
    assert desktop.services.tasks.get(task.id).title == "Still available"
    assert desktop.services.governance.list_audit() == []
    desktop.window.close()


def test_priority_explanation_uses_deterministic_fallback_when_ai_is_offline(
    qapp, tmp_path: Path
) -> None:
    desktop = make_desktop(qapp, tmp_path)
    task = desktop.services.task_service.create_task(
        **task_values("Deterministic focus", priority="High", due_date=date.today())
    )
    desktop.services.planning_service.model = UnavailableModel()  # type: ignore[assignment]
    output = QPlainTextEdit()

    desktop.window.tasks_view._explain(task, output)

    assert "Deterministic fallback" in output.toPlainText()
    assert "Due today; high priority." in output.toPlainText()
    desktop.window.close()


class ProposalModel:
    def model_identity(self):
        return "test-model"

    def fingerprint_configuration(self, resolved_model):
        return {"model": resolved_model}

    def propose_decomposition(self, contract, *, resolved_model=None):
        return json.dumps(
            {
                "proposal_type": "task_decomposition",
                "parent_task_id": contract["parent_task_id"],
                "proposal_id": contract["proposal_id"],
                "summary": "A reviewed two-step proposal.",
                "requires_confirmation": True,
                "subtasks": [
                    {
                        "item_key": "prepare",
                        "title": "Prepare inputs",
                        "description": "Prepare the required inputs.",
                        "estimated_hours": 1.0,
                        "priority": "Medium",
                        "suggested_sequence": 1,
                        "completion_criterion": "Inputs are ready.",
                        "due_date": None,
                        "prerequisite_item_keys": [],
                    },
                    {
                        "item_key": "finish",
                        "title": "Finish output",
                        "description": "Create and verify the output.",
                        "estimated_hours": 1.0,
                        "priority": "Medium",
                        "suggested_sequence": 2,
                        "completion_criterion": "Output is verified.",
                        "due_date": None,
                        "prerequisite_item_keys": ["prepare"],
                    },
                ],
                "advisories": [],
            }
        )


def test_ai_proposal_is_persisted_but_does_not_create_tasks_until_approval(
    qapp, tmp_path: Path
) -> None:
    desktop = make_desktop(qapp, tmp_path)
    parent = desktop.services.task_service.create_task(
        **task_values(
            "Plan migration",
            description="Migrate an existing workflow into the native application.",
            notes="The current service layer is ready.",
            completion_criterion="The workflow is tested.",
        )
    )
    desktop.services.planning_service.model = ProposalModel()  # type: ignore[assignment]
    before = len(desktop.services.tasks.list_all())

    result = desktop.services.planning_service.request_decomposition(parent, {})
    review = desktop.services.planning_service.get_review(result.proposal.proposal_id)
    assert review.status == "draft"
    assert len(desktop.services.tasks.list_all()) == before

    desktop.services.planning_service.approve_review(result.proposal.proposal_id)
    assert len(desktop.services.tasks.list_subtasks(parent.id)) == 2
    desktop.window.close()


def test_native_review_dialog_requires_explicit_confirmation_before_approval(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    desktop = make_desktop(qapp, tmp_path)
    parent = desktop.services.task_service.create_task(
        **task_values(
            "Review migration",
            description="Migrate and review an existing workflow.",
            notes="The service boundary is ready.",
            completion_criterion="The reviewed workflow is tested.",
        )
    )
    desktop.services.planning_service.model = ProposalModel()  # type: ignore[assignment]
    result = desktop.services.planning_service.request_decomposition(parent, {})
    dialog = ProposalReviewDialog(
        desktop.services,
        desktop.services.planning_service.get_review(result.proposal.proposal_id),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    assert desktop.services.tasks.list_subtasks(parent.id) == []
    dialog._approve()

    assert dialog.approved is True
    assert len(desktop.services.tasks.list_subtasks(parent.id)) == 2
    desktop.window.close()
