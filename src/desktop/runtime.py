from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from dotenv import load_dotenv

from src.runtime.bootstrap import bootstrap_runtime
from src.runtime.hardware import detect_hardware

# Phase 9A reuses the proven model lifecycle helpers while Streamlit remains a
# supported migration reference. Phase 9C can extract a shared public runtime
# boundary when the desktop launcher becomes authoritative.
from src.runtime.launcher import (
    _http_origin,
    _start_model,
    _stop_model_server,
    _verify_llm,
    load_runtime_config,
)



def _pyside6_available() -> bool:
    return importlib.util.find_spec("PySide6") is not None


def _run_qt_application(project_root: Path) -> int:
    from src.desktop.application import run_desktop_application

    return run_desktop_application(project_root)


def run() -> int:
    """Launch the Phase 9A native shell while preserving model ownership rules."""
    if not _pyside6_available():
        print(
            "PySide6 is not installed. Install requirements.txt before using --desktop.",
            flush=True,
        )
        return 1

    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")
    hardware = detect_hardware()

    print("Daybook AI desktop startup", flush=True)
    print("Checking local AI requirements...", flush=True)

    bootstrap = bootstrap_runtime(project_root, hardware)
    if bootstrap.llama_server:
        os.environ["DAYBOOK_LLAMA_SERVER"] = str(bootstrap.llama_server)
    else:
        os.environ.pop("DAYBOOK_LLAMA_SERVER", None)
    if bootstrap.model_path:
        os.environ["DAYBOOK_MODEL_PATH"] = str(bootstrap.model_path)
    os.environ.setdefault("DAYBOOK_GPU_LAYERS", str(bootstrap.gpu_layers))

    config = load_runtime_config(project_root, hardware)
    os.environ["DAYBOOK_MODEL_BASE_URL"] = (
        f"{_http_origin(config.model_host, config.model_port)}/v1"
    )
    os.environ["DAYBOOK_MODEL_API_KEY"] = config.model_api_key
    os.environ["DAYBOOK_DETECTED_GPU"] = hardware.gpu_name or "CPU only"
    os.environ["DAYBOOK_DETECTED_BACKEND"] = bootstrap.backend

    model_process, model_owned = _start_model(config)
    _verify_llm(config)

    try:
        return _run_qt_application(project_root)
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("PySide6"):
            print(
                "PySide6 is not installed. Install requirements.txt before using --desktop.",
                flush=True,
            )
            return 1
        raise
    finally:
        _stop_model_server(config, model_process, model_owned)
