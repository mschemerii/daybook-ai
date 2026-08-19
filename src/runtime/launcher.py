from __future__ import annotations

import argparse
import ipaddress
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from dotenv import load_dotenv

from src.runtime.bootstrap import bootstrap_runtime
from src.runtime.controller import ControllerConfig, ControllerServer
from src.runtime.hardware import HardwareInfo, detect_hardware
from src.runtime.state import (
    RuntimeState,
    remove_runtime_state,
    request_stop,
    status_runtime,
    write_runtime_state,
)

STREAMLIT_COMPAT_SPEC = "streamlit==1.56.0"
STREAMLIT_ASGI_CUTOFF = (1, 57, 0)


@dataclass(frozen=True)
class RuntimeConfig:
    project_root: Path
    model_path: Path | None
    llama_server: str | None
    model_host: str
    model_port: int
    streamlit_host: str
    streamlit_port: int
    controller_host: str
    controller_port: int
    context_size: int
    gpu_layers: int
    model_api_key: str
    controller_token: str


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start Daybook AI.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--screenshots",
        choices=("light", "dark", "both"),
        metavar="{light,dark,both}",
        help=(
            "Capture application screenshots using the selected theme, "
            "then stop services started by the launcher."
        ),
    )
    mode.add_argument(
        "--status",
        action="store_true",
        help="Report whether the managed Daybook AI application is running.",
    )
    mode.add_argument(
        "--stop",
        action="store_true",
        help="Request a graceful shutdown of the managed Daybook AI application.",
    )
    return parser.parse_args()


def _version_tuple(value: str) -> tuple[int, int, int]:
    parts: list[int] = []
    for token in value.split(".")[:3]:
        digits = "".join(character for character in token if character.isdigit())
        parts.append(int(digits or 0))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)  # type: ignore[return-value]


def _ensure_compatible_streamlit(project_root: Path) -> bool:
    try:
        installed = metadata.version("streamlit")
    except metadata.PackageNotFoundError:
        installed = None

    if installed is not None and _version_tuple(installed) < STREAMLIT_ASGI_CUTOFF:
        print(f"Compatible Streamlit detected: {installed}", flush=True)
        return True

    message = (
        "Streamlit is not installed."
        if installed is None
        else f"Streamlit {installed} is incompatible."
    )
    print(f"{message} Installing {STREAMLIT_COMPAT_SPEC}...", flush=True)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            STREAMLIT_COMPAT_SPEC,
        ],
        cwd=project_root,
        check=False,
    )
    return result.returncode == 0


def _is_http_ready(
    url: str,
    timeout: float = 0.75,
    api_key: str | None = None,
) -> bool:
    try:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _find_model(project_root: Path) -> Path | None:
    configured = os.getenv("DAYBOOK_MODEL_PATH", "").strip()
    if configured:
        path = Path(configured).expanduser()
        resolved = path if path.is_absolute() else (project_root / path).resolve()
        if resolved.exists():
            return resolved

    candidates = sorted((project_root / "models").rglob("*.gguf"))
    if candidates:
        preferred = [path for path in candidates if "Qwen3.5-0.8B" in path.name]
        return (preferred[0] if preferred else candidates[0]).resolve()
    return None


def _find_llama_server(project_root: Path) -> str | None:
    configured = os.getenv("DAYBOOK_LLAMA_SERVER", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if path.exists():
            return str(path.resolve())
        resolved = shutil.which(configured)
        if resolved:
            return resolved

    resolved = shutil.which("llama-server")
    if resolved:
        return resolved

    return None


def _require_loopback_host(name: str, value: str) -> str:
    normalized = value.strip()
    if normalized.lower() == "localhost":
        return normalized
    try:
        if ipaddress.ip_address(normalized).is_loopback:
            return normalized
    except ValueError:
        pass
    raise ValueError(
        f"{name} must use a loopback address; received {value!r}. "
        "Daybook AI v0.8 does not expose managed services to the network."
    )


def _http_origin(host: str, port: int) -> str:
    url_host = f"[{host}]" if ":" in host else host
    return f"http://{url_host}:{port}"


def load_runtime_config(
    project_root: Path,
    hardware: HardwareInfo,
) -> RuntimeConfig:
    load_dotenv(project_root / ".env")
    default_layers = 99 if hardware.gpu_available else 0
    model_host = _require_loopback_host(
        "DAYBOOK_MODEL_HOST",
        os.getenv("DAYBOOK_MODEL_HOST", "127.0.0.1"),
    )
    streamlit_host = _require_loopback_host(
        "DAYBOOK_STREAMLIT_HOST",
        os.getenv("DAYBOOK_STREAMLIT_HOST", "127.0.0.1"),
    )
    controller_host = _require_loopback_host(
        "DAYBOOK_CONTROLLER_HOST",
        os.getenv("DAYBOOK_CONTROLLER_HOST", "127.0.0.1"),
    )

    return RuntimeConfig(
        project_root=project_root,
        model_path=_find_model(project_root),
        llama_server=_find_llama_server(project_root),
        model_host=model_host,
        model_port=int(os.getenv("DAYBOOK_MODEL_PORT", "8080")),
        streamlit_host=streamlit_host,
        streamlit_port=int(os.getenv("DAYBOOK_STREAMLIT_PORT", "8501")),
        controller_host=controller_host,
        controller_port=int(os.getenv("DAYBOOK_CONTROLLER_PORT", "8500")),
        context_size=int(os.getenv("DAYBOOK_MODEL_CONTEXT_SIZE", "4096")),
        gpu_layers=int(os.getenv("DAYBOOK_GPU_LAYERS", str(default_layers))),
        model_api_key=os.getenv("DAYBOOK_MODEL_API_KEY", "").strip()
        or secrets.token_urlsafe(32),
        controller_token=os.getenv("DAYBOOK_CONTROLLER_TOKEN", "").strip()
        or secrets.token_urlsafe(32),
    )


def _start_model(
    config: RuntimeConfig,
) -> tuple[subprocess.Popen[str] | None, bool]:
    health_url = f"{_http_origin(config.model_host, config.model_port)}/v1/models"

    if _is_http_ready(health_url, api_key=config.model_api_key):
        print("Using the already-running local AI server.", flush=True)
        return None, False

    if not config.llama_server or not config.model_path:
        print(
            "Local AI prerequisites are unavailable. "
            "Daybook AI will start in limited mode.",
            flush=True,
        )
        return None, False

    command = [
        config.llama_server,
        "-m",
        str(config.model_path),
        "--host",
        config.model_host,
        "--port",
        str(config.model_port),
        "-c",
        str(config.context_size),
        "-ngl",
        str(config.gpu_layers),
        "--cors-origins",
        "localhost",
        "--no-cors-credentials",
        "--no-webui",
    ]

    print(f"Starting local model: {config.model_path.name}", flush=True)

    environment = os.environ.copy()
    environment["LLAMA_API_KEY"] = config.model_api_key
    process = subprocess.Popen(
        command,
        cwd=config.project_root,
        env=environment,
        text=True,
        start_new_session=True,
    )

    for _ in range(120):
        if process.poll() is not None:
            print("llama-server exited during startup.", flush=True)
            return process, True
        if _is_http_ready(health_url, api_key=config.model_api_key):
            print("Local AI server is ready.", flush=True)
            return process, True
        time.sleep(0.5)

    print("Local AI server did not become ready.", flush=True)
    return process, True


def _verify_llm(config: RuntimeConfig) -> bool:
    """Verify that llama.cpp can return a non-empty chat completion."""
    base_url = f"{_http_origin(config.model_host, config.model_port)}/v1"

    try:
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {config.model_api_key}"},
            ),
            timeout=5,
        ) as response:
            models_payload = response.read().decode("utf-8")

        import json

        models_data = json.loads(models_payload)
        model_entries = models_data.get("data", [])

        if not model_entries:
            raise RuntimeError("No model was reported by llama.cpp.")

        model_id = str(model_entries[0].get("id") or "local-model")

        request_body = json.dumps(
            {
                "model": model_id,
                "messages": [
                    {
                        "role": "user",
                        "content": "Reply with a short confirmation.",
                    }
                ],
                "temperature": 0,
                "max_tokens": 32,
                "stream": False,
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=request_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.model_api_key}",
            },
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=20) as response:
            completion_payload = response.read().decode("utf-8")

        completion_data = json.loads(completion_payload)
        choices = completion_data.get("choices", [])

        if not choices:
            raise RuntimeError("The model returned no completion choices.")

        message = choices[0].get("message", {})
        content = (
            message.get("content")
            or message.get("reasoning_content")
            or ""
        )

        if not str(content).strip():
            raise RuntimeError("The model returned an empty completion.")

        os.environ["DAYBOOK_MODEL_NAME"] = model_id
        os.environ["DAYBOOK_LLM_VERIFIED"] = "true"

        print(
            f"Local AI inference verified. Loaded model: {model_id}",
            flush=True,
        )
        return True

    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        ValueError,
        RuntimeError,
    ) as exc:
        os.environ["DAYBOOK_LLM_VERIFIED"] = "false"
        print(
            f"Local AI unavailable or unverified: {exc}",
            flush=True,
        )
        return False


def _start_streamlit(config: RuntimeConfig) -> subprocess.Popen[str] | None:
    if not _ensure_compatible_streamlit(config.project_root):
        return None

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.address",
        config.streamlit_host,
        "--server.port",
        str(config.streamlit_port),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
    ]

    print(f"Starting Streamlit with: {sys.executable}", flush=True)
    try:
        return subprocess.Popen(
            command,
            cwd=config.project_root,
            text=True,
            start_new_session=True,
        )
    except OSError as exc:
        print(f"ERROR: Streamlit could not be started: {exc}", flush=True)
        return None


def _wait_for_streamlit(
    config: RuntimeConfig,
    process: subprocess.Popen[str],
    timeout_seconds: int = 30,
) -> bool:
    url = _http_origin(config.streamlit_host, config.streamlit_port)
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        if process.poll() is not None:
            return False
        if _is_http_ready(url):
            return True
        time.sleep(0.25)

    return False


def _stop_process(
    process: subprocess.Popen[str] | None,
    label: str,
    timeout: float = 8.0,
) -> None:
    if process is None or process.poll() is not None:
        return

    print(f"Stopping {label}...", flush=True)
    process.terminate()

    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"{label} did not stop cleanly; forcing termination.", flush=True)
        process.kill()
        process.wait(timeout=3)

def _stop_model_server(
    config: RuntimeConfig,
    model_process: subprocess.Popen[str] | None,
    model_owned: bool,
) -> None:
    """Stop llama-server only when this launcher created the process."""
    if model_owned:
        _stop_process(model_process, "llama.cpp")
    else:
        print("Leaving the externally managed local AI server running.", flush=True)

def _capture_screenshots(
    project_root: Path,
    config: RuntimeConfig,
    theme: str,
) -> int:
    screenshot_script = project_root / "scripts" / "capture_pages.py"
    if not screenshot_script.exists():
        print(f"Screenshot script was not found: {screenshot_script}", flush=True)
        return 1

    completed = subprocess.run(
        [
            sys.executable,
            str(screenshot_script),
            "--theme",
            theme,
            "--url",
            f"http://{config.streamlit_host}:{config.streamlit_port}",
        ],
        cwd=project_root,
        check=False,
    )
    return completed.returncode


def run() -> int:
    args = parse_arguments()
    project_root = Path(__file__).resolve().parents[2]

    if getattr(args, "status", False):
        return status_runtime(project_root)

    if getattr(args, "stop", False):
        return request_stop(project_root)

    # Explicit .env and process-environment settings must be available before
    # bootstrap decides whether any runtime downloads are necessary.
    load_dotenv(project_root / ".env")
    hardware = detect_hardware()

    print("Daybook AI startup", flush=True)
    print("Checking local AI requirements...", flush=True)

    bootstrap = bootstrap_runtime(project_root, hardware)
    if bootstrap.llama_server:
        os.environ["DAYBOOK_LLAMA_SERVER"] = str(bootstrap.llama_server)
    else:
        # Never allow load_runtime_config() to rediscover an explicit runtime
        # that bootstrap already rejected.
        os.environ.pop("DAYBOOK_LLAMA_SERVER", None)
    if bootstrap.model_path:
        os.environ["DAYBOOK_MODEL_PATH"] = str(bootstrap.model_path)
    os.environ.setdefault("DAYBOOK_GPU_LAYERS", str(bootstrap.gpu_layers))

    config = load_runtime_config(project_root, hardware)

    model_base_url = f"{_http_origin(config.model_host, config.model_port)}/v1"
    controller_url = _http_origin(config.controller_host, config.controller_port)
    streamlit_url = _http_origin(config.streamlit_host, config.streamlit_port)

    os.environ["DAYBOOK_MODEL_BASE_URL"] = model_base_url
    os.environ["DAYBOOK_MODEL_API_KEY"] = config.model_api_key
    os.environ["DAYBOOK_DETECTED_GPU"] = hardware.gpu_name or "CPU only"
    os.environ["DAYBOOK_DETECTED_BACKEND"] = bootstrap.backend
    os.environ["DAYBOOK_CONTROLLER_URL"] = controller_url
    os.environ["DAYBOOK_CONTROLLER_TOKEN"] = config.controller_token

    print(
        f"Detected: {hardware.operating_system} {hardware.architecture}",
        flush=True,
    )
    print(f"Compute: {hardware.gpu_name or 'CPU only'}", flush=True)
    print(f"Backend: {bootstrap.backend}", flush=True)

    model_process, model_owned = _start_model(config)
    _verify_llm(config)

    streamlit_process = _start_streamlit(config)
    if streamlit_process is None:
        _stop_model_server(
            config,
            model_process,
            model_owned,
        )
        return 1

    if not _wait_for_streamlit(config, streamlit_process):
        print("Streamlit did not become ready.", flush=True)
        _stop_process(streamlit_process, "Streamlit")
        _stop_model_server(
            config,
            model_process,
            model_owned,
        )
        return 1

    if args.screenshots:
        result = _capture_screenshots(
            project_root,
            config,
            args.screenshots,
        )
        _stop_process(streamlit_process, "Streamlit")
        _stop_model_server(
            config,
            model_process,
            model_owned,
        )
        return result

    try:
        controller = ControllerServer(
            ControllerConfig(
                host=config.controller_host,
                port=config.controller_port,
                streamlit_url=streamlit_url,
                shutdown_token=config.controller_token,
            )
        )
        controller.start()
    except OSError as exc:
        print(
            f"Controller could not start on {controller_url}: {exc}",
            flush=True,
        )
        _stop_process(streamlit_process, "Streamlit")
        _stop_model_server(
            config,
            model_process,
            model_owned,
        )
        return 1

    controller.mark_streamlit_ready()

    try:
        write_runtime_state(
            project_root,
            RuntimeState(
                launcher_pid=os.getpid(),
                controller_url=controller.url,
                controller_token=config.controller_token,
                streamlit_url=streamlit_url,
                streamlit_pid=streamlit_process.pid,
                model_pid=(
                    model_process.pid
                    if model_owned and model_process is not None
                    else None
                ),
                model_owned=model_owned,
            ),
        )
    except OSError as exc:
        print(
            f"Runtime state could not be created: {exc}",
            flush=True,
        )
        controller.stop()
        _stop_process(streamlit_process, "Streamlit")
        _stop_model_server(
            config,
            model_process,
            model_owned,
        )
        return 1

    print(f"Opening Daybook AI: {controller.url}", flush=True)
    webbrowser.open_new_tab(controller.url)

    try:
        while streamlit_process.poll() is None:
            if controller.wait_for_shutdown(timeout=0.5):
                print("Shutdown requested from the browser.", flush=True)
                break
    except KeyboardInterrupt:
        print("\nShutdown requested from the terminal.", flush=True)
    finally:
        # Keep the controller page alive briefly so the goodbye page is fully
        # delivered before application services are stopped.
        time.sleep(1.25)

        _stop_process(streamlit_process, "Streamlit")
        _stop_model_server(
            config,
            model_process,
            model_owned,
        )

        # Leave the static goodbye page available for a few more seconds.
        time.sleep(3)
        controller.stop()
        remove_runtime_state(project_root)

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
