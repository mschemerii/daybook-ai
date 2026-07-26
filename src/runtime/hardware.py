from __future__ import annotations

import json
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class HardwareInfo:
    operating_system: str
    architecture: str
    gpu_vendor: str | None
    gpu_name: str | None
    recommended_backend: str
    gpu_available: bool
    evidence: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _run(command: list[str], timeout: float = 3.0) -> str:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (result.stdout or result.stderr or "").strip()


def _classify_gpu(text: str) -> tuple[str | None, str]:
    lowered = text.lower()
    if any(token in lowered for token in ("nvidia", "geforce", "quadro", "tesla")):
        return "NVIDIA", "CUDA"
    if any(token in lowered for token in ("advanced micro devices", "amd", "radeon")):
        return "AMD", "Vulkan or ROCm"
    if any(token in lowered for token in ("intel", "arc graphics", "iris", "uhd graphics")):
        return "Intel", "Vulkan, SYCL, or OpenVINO"
    if any(token in lowered for token in ("apple m1", "apple m2", "apple m3", "apple m4", "apple gpu")):
        return "Apple", "Metal"
    return None, "CPU"


def _mac_gpu() -> tuple[str, str] | None:
    output = _run(["system_profiler", "SPDisplaysDataType", "-json"], timeout=8.0)
    if not output:
        return None
    try:
        data = json.loads(output)
        displays = data.get("SPDisplaysDataType", [])
        for item in displays:
            name = item.get("sppci_model") or item.get("_name")
            if name:
                return str(name), output
    except json.JSONDecodeError:
        pass
    return None


def _windows_gpu() -> tuple[str, str] | None:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell:
        output = _run([
            powershell,
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name",
        ])
        names = [line.strip() for line in output.splitlines() if line.strip()]
        if names:
            preferred = next((name for name in names if "microsoft basic" not in name.lower()), names[0])
            return preferred, output
    return None


def _linux_gpu() -> tuple[str, str] | None:
    if shutil.which("nvidia-smi"):
        output = _run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
        if output:
            return output.splitlines()[0].strip(), output

    if shutil.which("lspci"):
        output = _run(["lspci"])
        gpu_lines = [
            line for line in output.splitlines()
            if any(token in line.lower() for token in ("vga compatible controller", "3d controller", "display controller"))
        ]
        if gpu_lines:
            preferred = next(
                (line for line in gpu_lines if any(v in line.lower() for v in ("nvidia", "amd", "radeon", "intel"))),
                gpu_lines[0],
            )
            return preferred.split(":", 2)[-1].strip(), "\n".join(gpu_lines)

    dri = Path("/dev/dri")
    if dri.exists():
        return "Linux graphics device", str(dri)
    return None


def detect_hardware() -> HardwareInfo:
    system = platform.system()
    architecture = platform.machine()
    detected: tuple[str, str] | None = None

    if system == "Darwin":
        detected = _mac_gpu()
        if detected is None and architecture.lower() in {"arm64", "aarch64"}:
            detected = (f"Apple Silicon ({architecture})", "Apple Silicon architecture")
    elif system == "Windows":
        detected = _windows_gpu()
    elif system == "Linux":
        detected = _linux_gpu()

    if detected:
        gpu_name, evidence = detected
        vendor, backend = _classify_gpu(gpu_name + "\n" + evidence)
        if system == "Darwin" and architecture.lower() in {"arm64", "aarch64"}:
            vendor, backend = "Apple", "Metal"
        return HardwareInfo(system, architecture, vendor or "Unknown", gpu_name, backend, True, evidence)

    return HardwareInfo(system, architecture, None, None, "CPU", False, "No supported GPU was detected.")
