from datetime import date
import pytest
from src.agent.local_llm import LocalModelClient, LocalModelError
from src.models.entities import Task, JournalEntry
from src.services.context_service import ContextService


def test_data_minimization(task_repo, journal_repo):
    task_repo.create(Task(None, "Secret detail", description="Should not be included", notes="Private", priority="High"))
    journal_repo.upsert(JournalEntry(date.today(), reflections="x" * 800))
    records, provenance = ContextService(task_repo, journal_repo).build(True, True, max_tasks=1, max_journals=1)
    task_record = next(r for r in records if r["type"] == "task")
    assert "description" not in task_record and "notes" not in task_record
    journal_record = next(r for r in records if r["type"] == "journal")
    assert len(journal_record["reflections"]) == 500
    assert provenance


def test_invalid_model_output():
    with pytest.raises(LocalModelError):
        LocalModelClient.parse_action_proposal("not json")
    with pytest.raises(LocalModelError):
        LocalModelClient.parse_action_proposal('{"action":"create_task"}')


def test_local_model_connection_failure(monkeypatch):
    import requests
    def fail(*args, **kwargs): raise requests.ConnectionError("offline")
    monkeypatch.setattr(requests, "get", fail)
    ok, msg = LocalModelClient("http://127.0.0.1:1/v1", "x").healthcheck()
    assert not ok and "unavailable" in msg.lower()


def test_healthcheck_verifies_real_inference_and_discovers_model(monkeypatch):
    class Response:
        def __init__(self, payload):
            self.payload = payload
        def raise_for_status(self):
            return None
        def json(self):
            return self.payload

    posts = []
    monkeypatch.setattr(
        "requests.get",
        lambda *args, **kwargs: Response({"data": [{"id": "qwen-local"}]}),
    )
    def fake_post(url, json, timeout):
        posts.append((url, json, timeout))
        return Response({"choices": [{"message": {"content": "Ready."}}]})
    monkeypatch.setattr("requests.post", fake_post)

    ok, message = LocalModelClient("http://127.0.0.1:8080/v1", "auto").healthcheck()

    assert ok
    assert "qwen-local" in message
    assert posts[0][0].endswith("/chat/completions")
    assert posts[0][1]["model"] == "qwen-local"



def test_healthcheck_accepts_reasoning_content(monkeypatch):
    class Response:
        def __init__(self, payload):
            self.payload = payload
        def raise_for_status(self):
            return None
        def json(self):
            return self.payload

    monkeypatch.setattr(
        "requests.get",
        lambda *args, **kwargs: Response({"data": [{"id": "qwen-local"}]}),
    )
    monkeypatch.setattr(
        "requests.post",
        lambda *args, **kwargs: Response({"choices": [{"message": {"content": "", "reasoning_content": "ready"}}]}),
    )

    ok, _ = LocalModelClient("http://127.0.0.1:8080/v1", "auto").healthcheck()
    assert ok

def test_chat_uses_discovered_model_and_local_endpoint(monkeypatch):
    class Response:
        def __init__(self, payload):
            self.payload = payload
        def raise_for_status(self):
            return None
        def json(self):
            return self.payload

    captured = {}
    monkeypatch.setattr(
        "requests.get",
        lambda *args, **kwargs: Response({"data": [{"id": "loaded-qwen"}]}),
    )
    def fake_post(url, json, timeout):
        captured.update({"url": url, "payload": json})
        return Response({"choices": [{"message": {"content": "Focus on the due task."}}]})
    monkeypatch.setattr("requests.post", fake_post)

    answer = LocalModelClient("http://127.0.0.1:8080/v1", "auto").chat(
        "What should I focus on?", [{"type": "task", "id": 1, "title": "Review plan"}]
    )

    assert answer == "Focus on the due task."
    assert captured["url"] == "http://127.0.0.1:8080/v1/chat/completions"
    assert captured["payload"]["model"] == "loaded-qwen"
    assert "Review plan" in captured["payload"]["messages"][1]["content"]
