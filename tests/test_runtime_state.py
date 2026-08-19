from __future__ import annotations

from pathlib import Path

from src.runtime import state as runtime_state


def sample_state() -> runtime_state.RuntimeState:
    return runtime_state.RuntimeState(
        launcher_pid=111,
        controller_url="http://127.0.0.1:8500",
        controller_token="controller-token",
        streamlit_url="http://127.0.0.1:8501",
        streamlit_pid=222,
        model_pid=333,
        model_owned=True,
    )


def test_runtime_state_round_trip(tmp_path: Path) -> None:
    expected = sample_state()

    runtime_state.write_runtime_state(tmp_path, expected)

    assert runtime_state.read_runtime_state(tmp_path) == expected

    runtime_state.remove_runtime_state(tmp_path)
    assert runtime_state.read_runtime_state(tmp_path) is None


def test_status_reports_running_instance(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    runtime_state.write_runtime_state(tmp_path, sample_state())
    monkeypatch.setattr(
        runtime_state,
        "_pid_is_running",
        lambda pid: True,
    )
    monkeypatch.setattr(
        runtime_state,
        "_url_ready",
        lambda url, timeout=0.75: True,
    )

    assert runtime_state.status_runtime(tmp_path) == 0

    output = capsys.readouterr().out
    assert "Daybook AI is running." in output
    assert "http://127.0.0.1:8500" in output
    assert "http://127.0.0.1:8501" in output


def test_stop_uses_authenticated_controller(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    expected = sample_state()
    runtime_state.write_runtime_state(tmp_path, expected)
    requested = []

    monkeypatch.setattr(
        runtime_state,
        "_request_controller_shutdown",
        lambda state: requested.append(state) or True,
    )
    monkeypatch.setattr(
        runtime_state,
        "_wait_for_managed_stop",
        lambda project_root, state, timeout_seconds=30.0: True,
    )

    assert runtime_state.request_stop(tmp_path) == 0
    assert requested == [expected]

    output = capsys.readouterr().out
    assert "Shutdown requested." in output
    assert "Daybook AI stopped cleanly." in output


def test_stop_is_idempotent_when_not_running(
    tmp_path: Path,
    capsys,
) -> None:
    assert runtime_state.request_stop(tmp_path) == 0
    assert "Daybook AI is not running." in capsys.readouterr().out
