from __future__ import annotations

import ipaddress
import json
import os
import secrets
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from src.runtime.hardware import HardwareInfo


@dataclass(frozen=True)
class RuntimeConfig:
    project_root: Path
    model_path: Path | None
    llama_server: str | None
    model_host: str
    model_port: int
    context_size: int
    gpu_layers: int
    model_api_key: str


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
        resolved_path = path if path.is_absolute() else project_root / path
        if resolved_path.exists():
            return str(resolved_path.resolve())
        resolved = shutil.which(configured)
        if resolved:
            return resolved
    return shutil.which("llama-server")


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
        "Daybook AI does not expose the managed model service to the network."
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
    return RuntimeConfig(
        project_root=project_root,
        model_path=_find_model(project_root),
        llama_server=_find_llama_server(project_root),
        model_host=model_host,
        model_port=int(os.getenv("DAYBOOK_MODEL_PORT", "8080")),
        context_size=int(os.getenv("DAYBOOK_MODEL_CONTEXT_SIZE", "4096")),
        gpu_layers=int(os.getenv("DAYBOOK_GPU_LAYERS", str(default_layers))),
        model_api_key=os.getenv("DAYBOOK_MODEL_API_KEY", "").strip()
        or secrets.token_urlsafe(32),
    )


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
    try:
        process = subprocess.Popen(
            command,
            cwd=config.project_root,
            env=environment,
            text=True,
            start_new_session=True,
        )
    except OSError as exc:
        print(f"llama-server could not be started: {exc}", flush=True)
        return None, False

    for _ in range(120):
        if process.poll() is not None:
            print("llama-server exited during startup.", flush=True)
            return process, True
        if _is_http_ready(health_url, api_key=config.model_api_key):
            print("Local AI server is ready.", flush=True)
            return process, True
        time.sleep(0.5)

    print("Local AI server did not become ready.", flush=True)
    _stop_process(process, "llama.cpp")
    return None, False


def _verify_llm(config: RuntimeConfig) -> bool:
    base_url = f"{_http_origin(config.model_host, config.model_port)}/v1"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {config.model_api_key}"},
            ),
            timeout=5,
        ) as response:
            models_data = json.loads(response.read().decode("utf-8"))

        model_entries = models_data.get("data", [])
        if not model_entries:
            raise RuntimeError("No model was reported by llama.cpp.")
        model_id = str(model_entries[0].get("id") or "local-model")

        request_body = json.dumps(
            {
                "model": model_id,
                "messages": [
                    {"role": "user", "content": "Reply with a short confirmation."}
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
            completion_data = json.loads(response.read().decode("utf-8"))

        choices = completion_data.get("choices", [])
        if not choices:
            raise RuntimeError("The model returned no completion choices.")
        message = choices[0].get("message", {})
        content = message.get("content") or message.get("reasoning_content") or ""
        if not str(content).strip():
            raise RuntimeError("The model returned an empty completion.")

        os.environ["DAYBOOK_MODEL_NAME"] = model_id
        os.environ["DAYBOOK_LLM_VERIFIED"] = "true"
        print(f"Local AI inference verified. Loaded model: {model_id}", flush=True)
        return True
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        ValueError,
        RuntimeError,
    ) as exc:
        os.environ["DAYBOOK_LLM_VERIFIED"] = "false"
        print(f"Local AI unavailable or unverified: {exc}", flush=True)
        return False


def _stop_model_server(
    config: RuntimeConfig,
    model_process: subprocess.Popen[str] | None,
    model_owned: bool,
) -> None:
    del config
    if model_owned:
        _stop_process(model_process, "llama.cpp")
    else:
        print("Leaving the externally managed local AI server running.", flush=True)
