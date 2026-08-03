from argparse import Namespace
from pathlib import Path

import pytest

from src.runtime import launcher
from src.runtime.bootstrap import BootstrapResult
from src.runtime.hardware import HardwareInfo
from src.runtime.launcher import RuntimeConfig


def test_unowned_model_server_is_never_stopped(monkeypatch):
    monkeypatch.setattr(
        launcher,
        "_stop_process",
        lambda *args, **kwargs: pytest.fail("external process must not be stopped"),
    )

    launcher._stop_model_server(None, None, False)  # type: ignore[arg-type]


def test_owned_model_server_uses_managed_process_handle(monkeypatch):
    calls = []
    process = object()
    monkeypatch.setattr(launcher, "_stop_process", lambda value, label: calls.append((value, label)))

    launcher._stop_model_server(None, process, True)  # type: ignore[arg-type]

    assert calls == [(process, "llama.cpp")]


def test_environment_is_loaded_before_bootstrap(monkeypatch):
    order = []

    monkeypatch.setattr(launcher, "parse_arguments", lambda: Namespace(screenshots=None))
    monkeypatch.setattr(launcher, "load_dotenv", lambda path: order.append("dotenv"))
    monkeypatch.setattr(launcher, "detect_hardware", lambda: order.append("hardware"))

    class StopAfterOrdering(Exception):
        pass

    def stop_bootstrap(*args, **kwargs):
        order.append("bootstrap")
        raise StopAfterOrdering

    monkeypatch.setattr(launcher, "bootstrap_runtime", stop_bootstrap)

    with pytest.raises(StopAfterOrdering):
        launcher.run()

    assert order == ["dotenv", "hardware", "bootstrap"]


def test_unvalidated_tools_executable_is_not_discovered(tmp_path: Path, monkeypatch):
    executable = tmp_path / "tools" / "llama.cpp" / "old" / "llama-server"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"unvalidated")
    monkeypatch.delenv("DAYBOOK_LLAMA_SERVER", raising=False)
    monkeypatch.setattr(launcher.shutil, "which", lambda value: None)

    assert launcher._find_llama_server(tmp_path) is None


def test_controller_constructor_failure_cleans_up_managed_processes(monkeypatch, tmp_path: Path):
    hardware = HardwareInfo("Linux", "x86_64", None, None, "CPU", False, "test")
    config = RuntimeConfig(
        project_root=tmp_path,
        model_path=tmp_path / "model.gguf",
        llama_server="llama-server",
        model_host="127.0.0.1",
        model_port=8080,
        streamlit_host="127.0.0.1",
        streamlit_port=8501,
        controller_host="127.0.0.1",
        controller_port=8500,
        context_size=4096,
        gpu_layers=0,
        model_api_key="model-token",
        controller_token="controller-token",
    )
    model_process = object()
    streamlit_process = object()
    stopped = []

    monkeypatch.setattr(launcher, "parse_arguments", lambda: Namespace(screenshots=None))
    monkeypatch.setattr(launcher, "load_dotenv", lambda path: None)
    monkeypatch.setattr(launcher, "detect_hardware", lambda: hardware)
    monkeypatch.setattr(
        launcher,
        "bootstrap_runtime",
        lambda *args, **kwargs: BootstrapResult(None, None, "CPU", 0, ()),
    )
    monkeypatch.setattr(launcher, "load_runtime_config", lambda *args: config)
    monkeypatch.setattr(launcher, "_start_model", lambda value: (model_process, True))
    monkeypatch.setattr(launcher, "_verify_llm", lambda value: True)
    monkeypatch.setattr(launcher, "_start_streamlit", lambda value: streamlit_process)
    monkeypatch.setattr(launcher, "_wait_for_streamlit", lambda *args: True)
    monkeypatch.setattr(
        launcher,
        "ControllerServer",
        lambda value: (_ for _ in ()).throw(OSError("port unavailable")),
    )
    monkeypatch.setattr(
        launcher,
        "_stop_process",
        lambda process, label: stopped.append((process, label)),
    )
    monkeypatch.setattr(
        launcher,
        "_stop_model_server",
        lambda runtime, process, owned: stopped.append((process, "llama.cpp")),
    )

    assert launcher.run() == 1
    assert stopped == [
        (streamlit_process, "Streamlit"),
        (model_process, "llama.cpp"),
    ]


def test_runtime_config_rejects_non_loopback_bind(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DAYBOOK_MODEL_HOST", "0.0.0.0")
    hardware = HardwareInfo("Linux", "x86_64", None, None, "CPU", False, "test")

    with pytest.raises(ValueError, match="loopback"):
        launcher.load_runtime_config(tmp_path, hardware)


def test_ipv6_loopback_url_is_bracketed():
    assert launcher._http_origin("::1", 8500) == "http://[::1]:8500"


def test_model_command_enforces_local_security(monkeypatch, tmp_path: Path):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"model")
    captured = {}

    class Process:
        def poll(self):
            return None

    config = RuntimeConfig(
        project_root=tmp_path,
        model_path=model,
        llama_server="llama-server",
        model_host="127.0.0.1",
        model_port=8080,
        streamlit_host="127.0.0.1",
        streamlit_port=8501,
        controller_host="127.0.0.1",
        controller_port=8500,
        context_size=4096,
        gpu_layers=0,
        model_api_key="secret-model-key",
        controller_token="controller-token",
    )
    readiness = iter([False, True])
    monkeypatch.setattr(launcher, "_is_http_ready", lambda *args, **kwargs: next(readiness))

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["environment"] = kwargs["env"]
        return Process()

    monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(launcher.time, "sleep", lambda value: None)

    process, owned = launcher._start_model(config)

    assert process is not None and owned
    assert "--cors-origins" in captured["command"]
    assert "localhost" in captured["command"]
    assert "--no-cors-credentials" in captured["command"]
    assert "--no-webui" in captured["command"]
    assert "--api-key" not in captured["command"]
    assert captured["environment"]["LLAMA_API_KEY"] == "secret-model-key"
