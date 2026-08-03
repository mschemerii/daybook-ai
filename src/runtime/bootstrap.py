from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src.runtime.hardware import HardwareInfo

PINNED_LLAMA_RELEASE = "b10217"
LLAMA_RELEASE_BASE_URL = (
    "https://github.com/ggml-org/llama.cpp/releases/download/"
    f"{PINNED_LLAMA_RELEASE}"
)
MODEL_REPO = "unsloth/Qwen3.5-0.8B-GGUF"
DEFAULT_MODEL_FILE = "Qwen3.5-0.8B-UD-Q4_K_XL.gguf"
MODEL_DOWNLOAD_URL = (
    "https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF/resolve/main/"
    f"{DEFAULT_MODEL_FILE}?download=true"
)

# SHA-256 values published by the official llama.cpp b10217 GitHub release.
# Only packages used by Daybook AI's supported runtime matrix are included.
PINNED_LLAMA_ASSETS = {
    "cudart-llama-bin-win-cuda-12.4-x64.zip": "8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6",
    "llama-b10217-bin-macos-arm64.tar.gz": "0e7b13c07c597d482f25b635b2da7a0be516db65a2548362d0caca7d2a6e6fc1",
    "llama-b10217-bin-macos-x64.tar.gz": "49c195b47e66d1ae4328217316756bff76e5985c0295ced86300cf51236cd883",
    "llama-b10217-bin-ubuntu-arm64.tar.gz": "f61469c48acd1d416cce82edab1b8b0a6e3306becfdb32177239fe5b43d4bb3f",
    "llama-b10217-bin-ubuntu-rocm-7.2-x64.tar.gz": "10232dc33c4cb504045a8e4c80880e2b4eafb6db3f91e21172f29f462d44699e",
    "llama-b10217-bin-ubuntu-vulkan-arm64.tar.gz": "4be1daa60bff8b48d7e06598de82ece353edbe0b0c1c8448368b8a7b42a8e563",
    "llama-b10217-bin-ubuntu-vulkan-x64.tar.gz": "b69529bceef077c22e474efc99558edf535a111da23b9c634e86754bc8197fcc",
    "llama-b10217-bin-ubuntu-x64.tar.gz": "b79145bfa48f4fef83e76e1cef7ef4fbdf966e497a2fd774f1107fc2a24500af",
    "llama-b10217-bin-win-cpu-arm64.zip": "6601df4750dd00641f95748bfd4c3a78188f628f2e9ccab0cdbc1e88d347ceb3",
    "llama-b10217-bin-win-cpu-x64.zip": "f60c9dca4ae90141884757100cf4994f72aab0ffabaccec1344a28163189bce8",
    "llama-b10217-bin-win-cuda-12.4-x64.zip": "dd9d505fdf527b0fbad9683581a2af59dda2782a51a346a9d391b9256b4a2af5",
    "llama-b10217-bin-win-hip-radeon-x64.zip": "04391895773af05a5375b438af3812b7a9b22a9ca67923a884e52c8c379dc4ab",
    "llama-b10217-bin-win-sycl-x64.zip": "5c45944acd10ed3e564d7730f17b879bf58a7e28eee51bd16f75c900a5ae6462",
}


@dataclass(frozen=True)
class BootstrapResult:
    llama_server: Path | None
    model_path: Path | None
    backend: str
    gpu_layers: int
    messages: tuple[str, ...]


@dataclass(frozen=True)
class LlamaPackage:
    backend: str
    asset_names: tuple[str, ...]


@dataclass(frozen=True)
class LlamaInspection:
    path: Path
    version_output: str
    devices_output: str
    backend: str
    gpu_layers: int


class ExecutableValidationError(RuntimeError):
    pass


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
    expected_sha256: str | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    reporter(f"Downloading {label}...")
    try:
        digest = hashlib.sha256()
        with urllib.request.urlopen(_request(url), timeout=60) as response, partial.open("wb") as output:
            total = int(response.headers.get("Content-Length", "0") or 0)
            received = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
                received += len(chunk)
                if total:
                    percent = min(100, int(received * 100 / total))
                    reporter(f"  {label}: {percent}% ({received // (1024 * 1024)} MB)")
        if expected_sha256 and digest.hexdigest() != expected_sha256.lower():
            raise RuntimeError(f"SHA-256 verification failed for {label}.")
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
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError("Unsafe symbolic link found in llama.cpp archive.")
        bundle.extractall(destination)


def _safe_extract_tar(archive: Path, destination: Path) -> None:
    destination_resolved = destination.resolve()
    with tarfile.open(archive, "r:*") as bundle:
        for member in bundle.getmembers():
            target = (destination / member.name).resolve()
            if destination_resolved not in target.parents and target != destination_resolved:
                raise ValueError("Unsafe path found in llama.cpp archive.")
            # Python's data filter rejects unsafe link targets, device files,
            # and other filesystem-specific archive features during extraction.
        bundle.extractall(destination, filter="data")


def _normalized_architecture(machine: str) -> str:
    normalized = machine.lower()
    if normalized in {"x86_64", "amd64"}:
        return "x64"
    if normalized in {"arm64", "aarch64"}:
        return "arm64"
    return normalized


def _package_for_hardware(hardware: HardwareInfo) -> LlamaPackage | None:
    system = hardware.operating_system.lower()
    architecture = _normalized_architecture(hardware.architecture)
    vendor = (hardware.gpu_vendor or "").lower()

    if system == "darwin" and architecture in {"arm64", "x64"}:
        return LlamaPackage(
            "Metal",
            (f"llama-{PINNED_LLAMA_RELEASE}-bin-macos-{architecture}.tar.gz",),
        )

    if system == "windows" and architecture == "arm64":
        return LlamaPackage(
            "CPU",
            (f"llama-{PINNED_LLAMA_RELEASE}-bin-win-cpu-arm64.zip",),
        )

    if system == "windows" and architecture == "x64":
        if vendor == "nvidia":
            return LlamaPackage(
                "CUDA",
                (
                    f"llama-{PINNED_LLAMA_RELEASE}-bin-win-cuda-12.4-x64.zip",
                    "cudart-llama-bin-win-cuda-12.4-x64.zip",
                ),
            )
        if vendor == "amd":
            return LlamaPackage(
                "HIP",
                (f"llama-{PINNED_LLAMA_RELEASE}-bin-win-hip-radeon-x64.zip",),
            )
        if vendor == "intel":
            return LlamaPackage(
                "SYCL",
                (f"llama-{PINNED_LLAMA_RELEASE}-bin-win-sycl-x64.zip",),
            )
        return LlamaPackage(
            "CPU",
            (f"llama-{PINNED_LLAMA_RELEASE}-bin-win-cpu-x64.zip",),
        )

    if system == "linux" and architecture == "arm64":
        backend = "Vulkan" if hardware.gpu_available and vendor else "CPU"
        suffix = "ubuntu-vulkan-arm64.tar.gz" if backend == "Vulkan" else "ubuntu-arm64.tar.gz"
        return LlamaPackage(backend, (f"llama-{PINNED_LLAMA_RELEASE}-bin-{suffix}",))

    if system == "linux" and architecture == "x64":
        if vendor == "amd":
            return LlamaPackage(
                "ROCm",
                (f"llama-{PINNED_LLAMA_RELEASE}-bin-ubuntu-rocm-7.2-x64.tar.gz",),
            )
        if vendor in {"nvidia", "intel"}:
            return LlamaPackage(
                "Vulkan",
                (f"llama-{PINNED_LLAMA_RELEASE}-bin-ubuntu-vulkan-x64.tar.gz",),
            )
        return LlamaPackage(
            "CPU",
            (f"llama-{PINNED_LLAMA_RELEASE}-bin-ubuntu-x64.tar.gz",),
        )
    return None


def _cpu_package_for_hardware(hardware: HardwareInfo) -> LlamaPackage | None:
    cpu_hardware = HardwareInfo(
        operating_system=hardware.operating_system,
        architecture=hardware.architecture,
        gpu_vendor=None,
        gpu_name=None,
        recommended_backend="CPU",
        gpu_available=False,
        evidence="CPU fallback requested.",
    )
    return _package_for_hardware(cpu_hardware)


def choose_llama_asset(assets: list[dict[str, object]], hardware: HardwareInfo) -> dict[str, object] | None:
    package = _package_for_hardware(hardware)
    if package is None:
        return None
    main_suffix = package.asset_names[0].replace(PINNED_LLAMA_RELEASE, "{release}")
    prefix, suffix = main_suffix.split("{release}")
    return next(
        (
            asset
            for asset in assets
            if str(asset.get("name", "")).startswith(prefix)
            and str(asset.get("name", "")).endswith(suffix)
        ),
        None,
    )


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _backend_visible(output: str, backend: str) -> bool:
    tokens = {
        "Metal": ("metal", "mtl"),
        "CUDA": ("cuda",),
        "HIP": ("hip", "rocm"),
        "ROCm": ("rocm", "hip"),
        "Vulkan": ("vulkan",),
        "SYCL": ("sycl",),
    }.get(backend, ())
    lowered = output.lower()
    return any(token in lowered for token in tokens)


def _configured_backend_preferences(hardware: HardwareInfo) -> tuple[str, ...]:
    vendor = (hardware.gpu_vendor or "").lower()
    if hardware.operating_system.lower() == "darwin":
        return ("Metal",)
    return {
        "nvidia": ("CUDA", "Vulkan"),
        "amd": ("ROCm", "HIP", "Vulkan"),
        "intel": ("SYCL", "Vulkan"),
        "apple": ("Metal",),
    }.get(vendor, ())


def _matches_pinned_release(version_output: str) -> bool:
    build_number = PINNED_LLAMA_RELEASE.removeprefix("b")
    return re.search(rf"\b{re.escape(build_number)}\b", version_output) is not None


def inspect_llama_server(
    path: Path,
    preferred_backend: str,
    compatible_backends: tuple[str, ...] = (),
) -> LlamaInspection | None:
    try:
        version = subprocess.run(
            [str(path), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if version.returncode != 0:
            return None
        version_output = (version.stdout or version.stderr or "").strip()
        if not version_output:
            return None

        devices = subprocess.run(
            [str(path), "--list-devices"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        devices_output = (devices.stdout or devices.stderr or "").strip()
    except (OSError, subprocess.SubprocessError):
        return None

    backend = "CPU"
    gpu_layers = 0
    if devices.returncode == 0:
        candidates = tuple(dict.fromkeys((preferred_backend, *compatible_backends)))
        visible = next(
            (
                candidate
                for candidate in candidates
                if candidate != "CPU"
                and _backend_visible(devices_output, candidate)
            ),
            None,
        )
        if visible:
            backend = visible
            gpu_layers = 99
    return LlamaInspection(path.resolve(), version_output, devices_output, backend, gpu_layers)


def _configured_llama_server(project_root: Path) -> Path | None:
    configured = os.getenv("DAYBOOK_LLAMA_SERVER", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_absolute():
            project_candidate = (project_root / candidate).resolve()
            if project_candidate.is_file():
                return project_candidate
        elif candidate.is_file():
            return candidate.resolve()
        resolved = shutil.which(configured)
        if resolved:
            return Path(resolved).resolve()

    resolved = shutil.which("llama-server")
    return Path(resolved).resolve() if resolved else None


def _read_compatible_manifest(
    install_dir: Path,
    hardware: HardwareInfo,
    package: LlamaPackage,
) -> Path | None:
    manifest_path = install_dir / "install-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("release") != PINNED_LLAMA_RELEASE:
            return None
        if manifest.get("operating_system") != hardware.operating_system:
            return None
        if manifest.get("architecture") != _normalized_architecture(hardware.architecture):
            return None
        if manifest.get("backend") != package.backend:
            return None
        if tuple(manifest.get("assets", ())) != package.asset_names:
            return None
        executable = (install_dir / str(manifest["executable"])).resolve()
        if install_dir.resolve() not in executable.parents or not executable.is_file():
            return None
        if _sha256_file(executable) != manifest.get("executable_sha256"):
            return None
        return executable
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _install_pinned_package(
    project_root: Path,
    hardware: HardwareInfo,
    package: LlamaPackage,
    reporter: Callable[[str], None],
) -> LlamaInspection:
    install_dir = (
        project_root
        / "tools"
        / "llama.cpp"
        / PINNED_LLAMA_RELEASE
        / f"{_normalized_architecture(hardware.architecture)}-{package.backend.lower()}"
    )
    cached = _read_compatible_manifest(install_dir, hardware, package)
    if cached:
        inspection = inspect_llama_server(cached, package.backend)
        cpu_package = _cpu_package_for_hardware(hardware)
        backend_unavailable = (
            package.backend != "CPU"
            and inspection is not None
            and inspection.backend == "CPU"
            and cpu_package != package
        )
        if (
            inspection
            and _matches_pinned_release(inspection.version_output)
            and not backend_unavailable
        ):
            reporter(f"Using validated llama.cpp {PINNED_LLAMA_RELEASE}: {cached}")
            return inspection
        reporter("The cached llama.cpp executable failed validation and will be replaced.")
        if backend_unavailable:
            raise ExecutableValidationError(
                f"The cached executable did not report {package.backend}."
            )

    with tempfile.TemporaryDirectory(prefix="daybook-llama-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        extracted = temp_dir / "extracted"
        extracted.mkdir()
        for asset_name in package.asset_names:
            digest = PINNED_LLAMA_ASSETS[asset_name]
            archive = temp_dir / asset_name
            _download(
                f"{LLAMA_RELEASE_BASE_URL}/{asset_name}",
                archive,
                asset_name,
                reporter,
                expected_sha256=digest,
            )
            if asset_name.lower().endswith(".zip"):
                _safe_extract_zip(archive, extracted)
            else:
                _safe_extract_tar(archive, extracted)

        server = _find_extracted_server(extracted)
        if not server:
            raise ExecutableValidationError(
                "The llama.cpp package did not contain llama-server."
            )
        inspection = inspect_llama_server(server, package.backend)
        if not inspection:
            raise ExecutableValidationError(
                "The downloaded llama-server executable failed validation."
            )
        if not _matches_pinned_release(inspection.version_output):
            raise ExecutableValidationError(
                "The downloaded llama-server reported an unexpected version."
            )
        cpu_package = _cpu_package_for_hardware(hardware)
        if (
            package.backend != "CPU"
            and inspection.backend == "CPU"
            and cpu_package != package
        ):
            raise ExecutableValidationError(
                f"The downloaded executable did not report {package.backend}."
            )

        if install_dir.exists():
            shutil.rmtree(install_dir)
        install_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(extracted), install_dir)

    installed_server = _find_extracted_server(install_dir)
    if not installed_server:
        raise ExecutableValidationError(
            "llama-server was lost while finalizing installation."
        )
    final_inspection = inspect_llama_server(installed_server, package.backend)
    if not final_inspection:
        raise ExecutableValidationError(
            "The installed llama-server executable failed validation."
        )
    if not _matches_pinned_release(final_inspection.version_output):
        raise ExecutableValidationError(
            "The installed llama-server reported an unexpected version."
        )

    manifest = {
        "release": PINNED_LLAMA_RELEASE,
        "assets": list(package.asset_names),
        "asset_sha256": {
            name: PINNED_LLAMA_ASSETS[name] for name in package.asset_names
        },
        "operating_system": hardware.operating_system,
        "architecture": _normalized_architecture(hardware.architecture),
        "backend": package.backend,
        "validated_backend": final_inspection.backend,
        "executable": str(installed_server.relative_to(install_dir)),
        "executable_sha256": _sha256_file(installed_server),
        "version_output": final_inspection.version_output,
    }
    (install_dir / "install-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    reporter(f"llama.cpp {PINNED_LLAMA_RELEASE} installed at {installed_server}")
    return final_inspection


def install_llama_cpp(
    project_root: Path,
    hardware: HardwareInfo,
    reporter: Callable[[str], None] = print,
) -> LlamaInspection | None:
    package = _package_for_hardware(hardware)
    if not package:
        raise RuntimeError(
            "No supported pinned llama.cpp package is available for "
            f"{hardware.operating_system} {hardware.architecture}."
        )

    configured = _configured_llama_server(project_root)
    if configured:
        inspection = inspect_llama_server(
            configured,
            package.backend,
            _configured_backend_preferences(hardware),
        )
        if inspection:
            reporter(f"Using configured llama.cpp: {configured}")
            if package.backend != "CPU" and inspection.backend == "CPU":
                reporter(
                    f"{package.backend} was not reported by --list-devices; "
                    "using CPU inference."
                )
            return inspection
        reporter(f"Configured llama.cpp failed executable validation: {configured}")

    reporter(
        f"Installing validated llama.cpp {PINNED_LLAMA_RELEASE} "
        f"for the {package.backend} backend..."
    )
    try:
        return _install_pinned_package(project_root, hardware, package, reporter)
    except ExecutableValidationError:
        cpu_package = _cpu_package_for_hardware(hardware)
        if not cpu_package or cpu_package == package:
            raise
        reporter(
            f"The {package.backend} executable could not run on this system; "
            "falling back to the pinned CPU package."
        )
        return _install_pinned_package(project_root, hardware, cpu_package, reporter)


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
    backend = "CPU"
    gpu_layers = 0

    try:
        model_path = install_model(project_root, report)
    except (OSError, RuntimeError, urllib.error.URLError) as exc:
        report(f"Model download failed: {exc}")
        report("Daybook AI will still start with task and journal features.")

    try:
        inspection = install_llama_cpp(project_root, hardware, report)
        if inspection:
            llama_server = inspection.path
            backend = inspection.backend
            gpu_layers = inspection.gpu_layers
    except (OSError, RuntimeError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
        report(f"llama.cpp installation failed: {exc}")
        report("Daybook AI will still start in limited mode.")

    return BootstrapResult(
        llama_server=llama_server,
        model_path=model_path,
        backend=backend,
        gpu_layers=gpu_layers,
        messages=tuple(messages),
    )
