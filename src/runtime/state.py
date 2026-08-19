"""Local runtime state used for safe command-line status and shutdown."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path


RUNTIME_STATE_FILENAME = ".daybook-runtime.json"


@dataclass(frozen=True)
class RuntimeState:
    launcher_pid: int
    controller_url: str
    controller_token: str
    streamlit_url: str
    streamlit_pid: int
    model_pid: int | None
    model_owned: bool


def runtime_state_path(project_root: Path) -> Path:
    return project_root / RUNTIME_STATE_FILENAME


def write_runtime_state(
    project_root: Path,
    state: RuntimeState,
) -> None:
    """Atomically persist the minimum data needed to manage this instance."""
    path = runtime_state_path(project_root)
    temporary_path = path.with_name(f"{path.name}.tmp")
    temporary_path.write_text(
        json.dumps(asdict(state), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    try:
        temporary_path.chmod(0o600)
    except OSError:
        # Windows permission semantics differ; the file remains local and
        # git-ignored even when POSIX mode bits are unavailable.
        pass
    temporary_path.replace(path)


def read_runtime_state(project_root: Path) -> RuntimeState | None:
    path = runtime_state_path(project_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        launcher_pid = int(payload["launcher_pid"])
        streamlit_pid = int(payload["streamlit_pid"])
        model_pid_value = payload.get("model_pid")
        state = RuntimeState(
            launcher_pid=launcher_pid,
            controller_url=str(payload["controller_url"]).rstrip("/"),
            controller_token=str(payload["controller_token"]),
            streamlit_url=str(payload["streamlit_url"]).rstrip("/"),
            streamlit_pid=streamlit_pid,
            model_pid=(
                int(model_pid_value)
                if model_pid_value is not None
                else None
            ),
            model_owned=bool(payload["model_owned"]),
        )
    except (
        FileNotFoundError,
        OSError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ):
        return None

    if (
        state.launcher_pid <= 0
        or state.streamlit_pid <= 0
        or not state.controller_url
        or not state.controller_token
        or not state.streamlit_url
    ):
        return None
    return state


def remove_runtime_state(project_root: Path) -> None:
    try:
        runtime_state_path(project_root).unlink()
    except FileNotFoundError:
        pass


def _url_ready(url: str, timeout: float = 0.75) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 500
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
    ):
        return False


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def status_runtime(project_root: Path) -> int:
    """Report the health of the launcher-managed Daybook instance."""
    state = read_runtime_state(project_root)
    if state is None:
        print("Daybook AI is not running.", flush=True)
        return 1

    launcher_running = _pid_is_running(state.launcher_pid)
    controller_ready = _url_ready(f"{state.controller_url}/health")
    streamlit_ready = _url_ready(state.streamlit_url)

    if launcher_running and controller_ready and streamlit_ready:
        print("Daybook AI is running.", flush=True)
        print(f"Controller: {state.controller_url}", flush=True)
        print(f"Streamlit: {state.streamlit_url}", flush=True)
        return 0

    if not launcher_running and not controller_ready and not streamlit_ready:
        remove_runtime_state(project_root)
        print("Daybook AI is not running. Removed stale runtime state.", flush=True)
        return 1

    print("Daybook AI is not fully running.", flush=True)
    print(
        "Launcher: "
        + ("running" if launcher_running else "stopped"),
        flush=True,
    )
    print(
        "Controller: "
        + ("ready" if controller_ready else "unavailable"),
        flush=True,
    )
    print(
        "Streamlit: "
        + ("ready" if streamlit_ready else "unavailable"),
        flush=True,
    )
    return 1


def _request_controller_shutdown(state: RuntimeState) -> bool:
    query = urllib.parse.urlencode({"token": state.controller_token})
    request_url = f"{state.controller_url}/shutdown?{query}"
    try:
        with urllib.request.urlopen(request_url, timeout=5) as response:
            response.read()
            return 200 <= response.status < 500
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
    ):
        return False


def _wait_for_managed_stop(
    project_root: Path,
    state: RuntimeState,
    timeout_seconds: float = 30.0,
) -> bool:
    deadline = time.time() + timeout_seconds
    path = runtime_state_path(project_root)

    while time.time() < deadline:
        if not path.exists():
            return True
        if (
            not _pid_is_running(state.launcher_pid)
            and not _url_ready(state.streamlit_url)
        ):
            remove_runtime_state(project_root)
            return True
        time.sleep(0.25)

    return False


def request_stop(project_root: Path) -> int:
    """Request graceful shutdown through the authenticated local controller."""
    state = read_runtime_state(project_root)
    if state is None:
        print("Daybook AI is not running.", flush=True)
        return 0

    if not _request_controller_shutdown(state):
        if (
            not _pid_is_running(state.launcher_pid)
            and not _url_ready(state.streamlit_url)
        ):
            remove_runtime_state(project_root)
            print("Daybook AI is not running. Removed stale runtime state.", flush=True)
            return 0

        print(
            "Daybook AI controller is not reachable; "
            "no unmanaged process was terminated.",
            flush=True,
        )
        return 1

    print("Shutdown requested.", flush=True)

    if _wait_for_managed_stop(project_root, state):
        print("Daybook AI stopped cleanly.", flush=True)
        return 0

    print(
        "Daybook AI did not finish shutting down within 30 seconds.",
        flush=True,
    )
    return 1
