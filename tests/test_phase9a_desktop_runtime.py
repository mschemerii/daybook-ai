from __future__ import annotations

from pathlib import Path

import pytest

from src.desktop import runtime
from src.runtime.bootstrap import BootstrapResult
from src.runtime.hardware import HardwareInfo
from src.runtime.model_runtime import RuntimeConfig


@pytest.fixture
def runtime_config(tmp_path: Path) -> RuntimeConfig:
    return RuntimeConfig(
        project_root=tmp_path,
        model_path=None,
        llama_server=None,
        model_host="127.0.0.1",
        model_port=8080,
        context_size=4096,
        gpu_layers=0,
        model_api_key="model-token",
    )


def _prepare_runtime(monkeypatch, runtime_config: RuntimeConfig) -> None:
    monkeypatch.setattr(runtime, "_pyside6_available", lambda: True)
    hardware = HardwareInfo("Linux", "x86_64", None, None, "CPU", False, "test")
    monkeypatch.setattr(runtime, "load_dotenv", lambda path: None)
    monkeypatch.setattr(runtime, "detect_hardware", lambda: hardware)
    monkeypatch.setattr(
        runtime,
        "bootstrap_runtime",
        lambda *args, **kwargs: BootstrapResult(None, None, "CPU", 0, ()),
    )
    monkeypatch.setattr(runtime, "load_runtime_config", lambda *args: runtime_config)


def test_desktop_runtime_missing_pyside_fails_before_runtime_bootstrap(
    monkeypatch,
) -> None:
    monkeypatch.setattr(runtime, "_pyside6_available", lambda: False)
    monkeypatch.setattr(
        runtime,
        "detect_hardware",
        lambda: pytest.fail("missing PySide6 must fail before hardware/runtime bootstrap"),
    )

    assert runtime.run() == 1


def test_desktop_runtime_stops_only_owned_model(
    monkeypatch,
    runtime_config: RuntimeConfig,
) -> None:
    _prepare_runtime(monkeypatch, runtime_config)
    process = object()
    stopped = []
    monkeypatch.setattr(runtime, "_start_model", lambda config: (process, True))
    monkeypatch.setattr(runtime, "_verify_llm", lambda config: True)
    monkeypatch.setattr(runtime, "_run_qt_application", lambda root: 0)
    monkeypatch.setattr(
        runtime,
        "_stop_model_server",
        lambda config, model_process, owned: stopped.append((model_process, owned)),
    )

    assert runtime.run() == 0
    assert stopped == [(process, True)]


def test_desktop_runtime_continues_when_model_is_unavailable(
    monkeypatch,
    runtime_config: RuntimeConfig,
) -> None:
    _prepare_runtime(monkeypatch, runtime_config)
    stopped = []
    monkeypatch.setattr(runtime, "_start_model", lambda config: (None, False))
    monkeypatch.setattr(runtime, "_verify_llm", lambda config: False)
    monkeypatch.setattr(runtime, "_run_qt_application", lambda root: 0)
    monkeypatch.setattr(
        runtime,
        "_stop_model_server",
        lambda config, model_process, owned: stopped.append((model_process, owned)),
    )

    assert runtime.run() == 0
    assert stopped == [(None, False)]



def test_desktop_runtime_cleans_owned_model_when_qt_startup_fails(
    monkeypatch,
    runtime_config: RuntimeConfig,
) -> None:
    _prepare_runtime(monkeypatch, runtime_config)
    process = object()
    stopped = []
    monkeypatch.setattr(runtime, "_start_model", lambda config: (process, True))
    monkeypatch.setattr(runtime, "_verify_llm", lambda config: True)
    monkeypatch.setattr(
        runtime,
        "_run_qt_application",
        lambda root: (_ for _ in ()).throw(RuntimeError("Qt startup failed")),
    )
    monkeypatch.setattr(
        runtime,
        "_stop_model_server",
        lambda config, model_process, owned: stopped.append((model_process, owned)),
    )

    with pytest.raises(RuntimeError, match="Qt startup failed"):
        runtime.run()

    assert stopped == [(process, True)]


def test_desktop_runtime_repeated_start_close_releases_each_owned_model(
    monkeypatch,
    runtime_config: RuntimeConfig,
) -> None:
    _prepare_runtime(monkeypatch, runtime_config)
    processes = iter([object(), object()])
    stopped = []
    monkeypatch.setattr(runtime, "_start_model", lambda config: (next(processes), True))
    monkeypatch.setattr(runtime, "_verify_llm", lambda config: True)
    monkeypatch.setattr(runtime, "_run_qt_application", lambda root: 0)
    monkeypatch.setattr(
        runtime,
        "_stop_model_server",
        lambda config, model_process, owned: stopped.append((model_process, owned)),
    )

    assert runtime.run() == 0
    assert runtime.run() == 0
    assert len(stopped) == 2
    assert all(owned for _, owned in stopped)


def test_desktop_runtime_preserves_external_model_on_qt_failure(
    monkeypatch,
    runtime_config: RuntimeConfig,
) -> None:
    _prepare_runtime(monkeypatch, runtime_config)
    stopped = []
    monkeypatch.setattr(runtime, "_start_model", lambda config: (None, False))
    monkeypatch.setattr(runtime, "_verify_llm", lambda config: True)
    monkeypatch.setattr(
        runtime,
        "_run_qt_application",
        lambda root: (_ for _ in ()).throw(RuntimeError("Qt startup failed")),
    )
    monkeypatch.setattr(
        runtime,
        "_stop_model_server",
        lambda config, model_process, owned: stopped.append((model_process, owned)),
    )

    with pytest.raises(RuntimeError, match="Qt startup failed"):
        runtime.run()

    assert stopped == [(None, False)]
