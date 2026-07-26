from __future__ import annotations

import json
import os
import platform
import shutil
import stat
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.runtime.hardware import HardwareInfo

LLAMA_RELEASE_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
MODEL_REPO = "unsloth/Qwen3.5-0.8B-GGUF"
DEFAULT_MODEL_FILE = "Qwen3.5-0.8B-UD-Q4_K_XL.gguf"
MODEL_DOWNLOAD_URL = (
    "https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF/resolve/main/"
    f"{DEFAULT_MODEL_FILE}?download=true"
)


@dataclass(frozen=True)
class BootstrapResult:
    llama_server: Path | None
    model_path: Path | None
    messages: tuple[str, ...]


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": "Daybook-AI-bootstrap/1.0",
            "Accept": "application/vnd.github+json",
        },
    )


def _download(
    url: str,
    destination: Path,
    label: str,
    reporter: Callable[[str], None] = print,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    reporter(f"Downloading {label}...")
    try:
        with urllib.request.urlopen(_request(url), timeout=60) as response, partial.open("wb") as output:
            total = int(response.headers.get("Content-Length", "0") or 0)
            received = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                received += len(chunk)
                if total:
                    percent = min(100, int(received * 100 / total))
                    reporter(f"  {label}: {percent}% ({received // (1024 * 1024)} MB)")
        partial.replace(destination)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    reporter(f"Saved {label} to {destination}")
    return destination


def _safe_extract_zip(archive: Path, destination: Path) -> None:
    destination_resolved = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if destination_resolved not in target.parents and target != destination_resolved:
                raise ValueError("Unsafe path found in llama.cpp archive.")
        bundle.extractall(destination)


def _safe_extract_tar(archive: Path, destination: Path) -> None:
    destination_resolved = destination.resolve()
    with tarfile.open(archive, "r:*") as bundle:
        for member in bundle.getmembers():
            target = (destination / member.name).resolve()
            if destination_resolved not in target.parents and target != destination_resolved:
                raise ValueError("Unsafe path found in llama.cpp archive.")
        bundle.extractall(destination)


def _architecture_tokens(machine: str) -> tuple[str, ...]:
    normalized = machine.lower()
    if normalized in {"x86_64", "amd64"}:
        return ("x64", "x86_64", "amd64")
    if normalized in {"arm64", "aarch64"}:
        return ("arm64", "aarch64")
    return (normalized,)


def _asset_score(name: str, hardware: HardwareInfo) -> int:
    lowered = name.lower()
    system = hardware.operating_system.lower()
    score = 0

    if not lowered.endswith((".zip", ".tar.gz", ".tgz")):
        return -10_000

    os_tokens = {
        "windows": ("win", "windows"),
        "darwin": ("macos", "darwin", "osx"),
        "linux": ("ubuntu", "linux"),
    }.get(system, (system,))
    if any(token in lowered for token in os_tokens):
        score += 100
    else:
        return -10_000

    if any(token in lowered for token in _architecture_tokens(hardware.architecture)):
        score += 40
    else:
        score -= 30

    vendor = (hardware.gpu_vendor or "").lower()
    backend_preferences = {
        "nvidia": ("cuda",),
        "amd": ("hip", "vulkan"),
        "intel": ("sycl", "vulkan"),
        "apple": ("metal",),
    }.get(vendor, ())

    if backend_preferences and any(token in lowered for token in backend_preferences):
        score += 35
    if "cpu" in lowered:
        score += 10
    if "cuda" in lowered and vendor != "nvidia":
        score -= 50
    if "hip" in lowered and vendor != "amd":
        score -= 40

    # Prefer the main binaries over dependency-only packages.
    if any(token in lowered for token in ("cudart", "dlls", "runtime")):
        score -= 60
    if "llama" in lowered:
        score += 5
    return score


def choose_llama_asset(assets: list[dict[str, object]], hardware: HardwareInfo) -> dict[str, object] | None:
    ranked = sorted(
        assets,
        key=lambda asset: _asset_score(str(asset.get("name", "")), hardware),
        reverse=True,
    )
    if not ranked or _asset_score(str(ranked[0].get("name", "")), hardware) < 0:
        return None
    return ranked[0]


def _find_extracted_server(directory: Path) -> Path | None:
    names = {"llama-server", "llama-server.exe"}
    candidates = [path for path in directory.rglob("*") if path.is_file() and path.name in names]
    if not candidates:
        return None
    candidates.sort(key=lambda path: (len(path.parts), str(path)))
    server = candidates[0]
    if os.name != "nt":
        server.chmod(server.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return server


def install_llama_cpp(
    project_root: Path,
    hardware: HardwareInfo,
    reporter: Callable[[str], None] = print,
) -> Path | None:
    install_dir = project_root / "tools" / "llama.cpp"
    existing = _find_extracted_server(install_dir) if install_dir.exists() else None
    if existing:
        reporter(f"Using existing llama.cpp: {existing}")
        return existing

    # Reuse a llama.cpp installation from a sibling Daybook AI extraction.
    for sibling in sorted(project_root.parent.glob("daybook-ai*")):
        if sibling.resolve() == project_root.resolve() or not sibling.is_dir():
            continue
        sibling_install = sibling / "tools" / "llama.cpp"
        existing = _find_extracted_server(sibling_install) if sibling_install.exists() else None
        if existing:
            reporter(f"Using existing llama.cpp from {sibling.name}: {existing}")
            return existing

    reporter("llama.cpp was not found. Installing an official prebuilt release locally...")
    with urllib.request.urlopen(_request(LLAMA_RELEASE_API), timeout=30) as response:
        release = json.load(response)
    asset = choose_llama_asset(list(release.get("assets", [])), hardware)
    if not asset:
        raise RuntimeError(
            f"No compatible llama.cpp release asset was found for "
            f"{hardware.operating_system} {hardware.architecture}."
        )

    asset_name = str(asset["name"])
    asset_url = str(asset["browser_download_url"])
    reporter(f"Selected llama.cpp package: {asset_name}")

    install_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="daybook-llama-") as temp_dir:
        archive = Path(temp_dir) / asset_name
        _download(asset_url, archive, "llama.cpp", reporter)
        if asset_name.lower().endswith(".zip"):
            _safe_extract_zip(archive, install_dir)
        else:
            _safe_extract_tar(archive, install_dir)

    server = _find_extracted_server(install_dir)
    if not server:
        raise RuntimeError("The llama.cpp package downloaded, but llama-server was not found inside it.")
    reporter(f"llama.cpp installed at {server}")
    return server


def find_existing_model(project_root: Path) -> Path | None:
    configured = os.getenv("DAYBOOK_MODEL_PATH", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_absolute():
            candidate = project_root / candidate
        if candidate.exists() and candidate.suffix.lower() == ".gguf":
            return candidate.resolve()

    candidates = sorted((project_root / "models").rglob("*.gguf"))
    if candidates:
        preferred = [path for path in candidates if "Qwen3.5-0.8B" in path.name]
        return (preferred[0] if preferred else candidates[0]).resolve()

    # Reuse models from sibling Daybook AI extractions to avoid redownloading.
    sibling_candidates: list[Path] = []
    for sibling in sorted(project_root.parent.glob("daybook-ai*")):
        if sibling.resolve() == project_root.resolve() or not sibling.is_dir():
            continue
        sibling_candidates.extend(sorted((sibling / "models").rglob("*.gguf")))
    if sibling_candidates:
        preferred = [path for path in sibling_candidates if "Qwen3.5-0.8B" in path.name]
        return (preferred[0] if preferred else sibling_candidates[0]).resolve()
    return None


def install_model(
    project_root: Path,
    reporter: Callable[[str], None] = print,
) -> Path:
    existing = find_existing_model(project_root)
    if existing:
        reporter(f"Using existing model: {existing.name}")
        return existing

    model_dir = project_root / "models"
    destination = model_dir / DEFAULT_MODEL_FILE
    reporter(f"No GGUF model was found. Downloading {MODEL_REPO}.")
    return _download(MODEL_DOWNLOAD_URL, destination, DEFAULT_MODEL_FILE, reporter)


def bootstrap_runtime(
    project_root: Path,
    hardware: HardwareInfo,
    reporter: Callable[[str], None] = print,
) -> BootstrapResult:
    messages: list[str] = []

    def report(message: str) -> None:
        messages.append(message)
        reporter(message)

    model_path: Path | None = None
    llama_server: Path | None = None

    try:
        model_path = install_model(project_root, report)
    except (OSError, RuntimeError, urllib.error.URLError) as exc:
        report(f"Model download failed: {exc}")
        report("Daybook AI will still start with task and journal features.")

    try:
        llama_server = install_llama_cpp(project_root, hardware, report)
    except (OSError, RuntimeError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
        report(f"llama.cpp installation failed: {exc}")
        report("Daybook AI will still start in limited mode.")

    return BootstrapResult(llama_server, model_path, tuple(messages))
