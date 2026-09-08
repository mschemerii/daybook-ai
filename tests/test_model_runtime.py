from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from src.runtime import model_runtime
from src.runtime.hardware import HardwareInfo
from src.runtime.model_runtime import RuntimeConfig


def make_config(tmp_path: Path, **overrides) -> RuntimeConfig:
    values = dict(
        project_root=tmp_path,
        model_path=None,
        llama_server=None,
        model_host="127.0.0.1",
        model_port=8080,
        context_size=4096,
        gpu_layers=0,
        model_api_key="model-token",
    )
    values.update(overrides)
    return RuntimeConfig(**values)


def test_unowned_model_server_is_never_stopped(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        model_runtime,
        "_stop_process",
        lambda *args, **kwargs: pytest.fail("external process must not be stopped"),
    )
    model_runtime._stop_model_server(make_config(tmp_path), None, False)


def test_owned_model_server_uses_managed_process_handle(monkeypatch, tmp_path: Path):
    calls = []
    process = object()
    monkeypatch.setattr(
        model_runtime,
        "_stop_process",
        lambda value, label: calls.append((value, label)),
    )
    model_runtime._stop_model_server(
        make_config(tmp_path), process, True  # type: ignore[arg-type]
    )
    assert calls == [(process, "llama.cpp")]


def test_owned_model_process_is_reaped(tmp_path: Path) -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        text=True,
        start_new_session=True,
    )
    model_runtime._stop_model_server(make_config(tmp_path), process, True)
    assert process.poll() is not None


def test_external_model_process_is_preserved(tmp_path: Path) -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        text=True,
        start_new_session=True,
    )
    try:
        model_runtime._stop_model_server(make_config(tmp_path), process, False)
        assert process.poll() is None
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_unvalidated_tools_executable_is_not_discovered(tmp_path: Path, monkeypatch):
    executable = tmp_path / "tools" / "llama.cpp" / "old" / "llama-server"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"unvalidated")
    monkeypatch.delenv("DAYBOOK_LLAMA_SERVER", raising=False)
    monkeypatch.setattr(model_runtime.shutil, "which", lambda value: None)
    assert model_runtime._find_llama_server(tmp_path) is None


def test_runtime_config_rejects_non_loopback_bind(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DAYBOOK_MODEL_HOST", "0.0.0.0")
    hardware = HardwareInfo("Linux", "x86_64", None, None, "CPU", False, "test")
    with pytest.raises(ValueError, match="loopback"):
        model_runtime.load_runtime_config(tmp_path, hardware)


def test_ipv6_loopback_url_is_bracketed():
    assert model_runtime._http_origin("::1", 8080) == "http://[::1]:8080"


def test_model_command_enforces_local_security(monkeypatch, tmp_path: Path):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"model")
    captured = {}

    class Process:
        def poll(self):
            return None

    config = make_config(
        tmp_path,
        model_path=model,
        llama_server="llama-server",
        model_api_key="secret-model-key",
    )
    readiness = iter([False, True])
    monkeypatch.setattr(
        model_runtime, "_is_http_ready", lambda *args, **kwargs: next(readiness)
    )

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["environment"] = kwargs["env"]
        return Process()

    monkeypatch.setattr(model_runtime.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(model_runtime.time, "sleep", lambda value: None)

    process, owned = model_runtime._start_model(config)

    assert process is not None and owned
    assert "--cors-origins" in captured["command"]
    assert "localhost" in captured["command"]
    assert "--no-cors-credentials" in captured["command"]
    assert "--no-webui" in captured["command"]
    assert "--api-key" not in captured["command"]
    assert captured["environment"]["LLAMA_API_KEY"] == "secret-model-key"


def test_model_start_failure_returns_limited_mode(monkeypatch, tmp_path: Path):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"model")
    config = make_config(
        tmp_path,
        model_path=model,
        llama_server="missing-llama-server",
    )
    monkeypatch.setattr(model_runtime, "_is_http_ready", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        model_runtime.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("not executable")),
    )
    assert model_runtime._start_model(config) == (None, False)


def test_model_readiness_timeout_stops_owned_process(monkeypatch, tmp_path: Path):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"model")
    config = make_config(tmp_path, model_path=model, llama_server="llama-server")

    class Process:
        def poll(self):
            return None

    process = Process()
    stopped = []
    monkeypatch.setattr(model_runtime, "_is_http_ready", lambda *args, **kwargs: False)
    monkeypatch.setattr(model_runtime.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(model_runtime.time, "sleep", lambda value: None)
    monkeypatch.setattr(
        model_runtime,
        "_stop_process",
        lambda candidate, label: stopped.append((candidate, label)),
    )

    assert model_runtime._start_model(config) == (None, False)
    assert stopped == [(process, "llama.cpp")]
