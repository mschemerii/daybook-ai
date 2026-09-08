from tests.lifecycle_helpers import recorded_task


def test_completed_tasks_can_be_reopened(task_repo, task_service):
    created = recorded_task(task_service, title="Finished")
    completed = task_service.completed()
    assert [task.id for task in completed] == [created.id]

    reopened = task_service.reopen_task(created.id)
    assert reopened.status == "Open"
    assert task_service.completed() == []
