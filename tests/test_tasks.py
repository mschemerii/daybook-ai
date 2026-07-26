from datetime import date, timedelta
from src.models.entities import Task, ProposedAction


def test_database_crud(task_repo):
    created = task_repo.create(Task(None, "Test", priority="High"))
    assert created.id
    assert task_repo.get(created.id).title == "Test"
    task_repo.update(created.id, {"title": "Updated"})
    assert task_repo.get(created.id).title == "Updated"
    task_repo.delete(created.id)
    assert task_repo.list_all() == []


def test_prioritization(task_repo, task_service):
    today = date.today()
    task_repo.create(Task(None, "Future high", priority="High", due_date=today + timedelta(days=2)))
    task_repo.create(Task(None, "Today low", priority="Low", due_date=today))
    task_repo.create(Task(None, "Overdue medium", priority="Medium", due_date=today - timedelta(days=1)))
    task_repo.create(Task(None, "Blocked overdue", priority="High", due_date=today - timedelta(days=2), status="Blocked"))
    assert [t.title for t in task_service.focus_items(today)] == ["Overdue medium", "Today low", "Future high"]


def test_confirmation_required(task_service):
    proposal = ProposedAction("create_task", {"title": "AI proposal"}, "Requested", True)
    result = task_service.apply_confirmed_proposal(proposal)
    assert result.title == "AI proposal"


def test_confirmation_cannot_be_bypassed(task_service):
    proposal = ProposedAction("create_task", {"title": "Bad"}, "Requested", False)
    try:
        task_service.apply_confirmed_proposal(proposal)
        assert False
    except PermissionError:
        assert True


def test_prohibited_action(task_service):
    proposal = ProposedAction("send_email", {}, "No", True)
    try:
        task_service.apply_confirmed_proposal(proposal)
        assert False
    except PermissionError:
        assert True


def test_provenance_preserved(task_repo):
    task = task_repo.create(Task(None, "Imported", source="Meeting notes"))
    assert task.source == "Meeting notes"
