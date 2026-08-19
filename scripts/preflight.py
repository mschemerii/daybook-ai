from __future__ import annotations

import argparse
import ctypes
import importlib.metadata
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SUPPORTED_PYTHON = (3, 12)
RECOMMENDED_FREE_DISK_GIB = 4.0
RECOMMENDED_RAM_GIB = 4.0


def _version_tuple(value: str) -> tuple[int, int, int]:
    numbers = [int(part) for part in re.findall(r"\d+", value)[:3]]
    while len(numbers) < 3:
        numbers.append(0)
    return tuple(numbers)  # type: ignore[return-value]


def _total_ram_bytes() -> int | None:
    system = platform.system()

    if system == "Windows":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullTotalPhys)
        except (AttributeError, OSError):
            return None
        return None

    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        if isinstance(pages, int) and isinstance(page_size, int):
            return pages * page_size
    except (AttributeError, OSError, ValueError):
        pass

    if system == "Darwin":
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip().isdigit():
                return int(result.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            pass

    return None


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _verify_dependencies() -> list[str]:
    errors: list[str] = []

    streamlit = _package_version("streamlit")
    requests = _package_version("requests")
    dotenv = _package_version("python-dotenv")

    if streamlit != "1.56.0":
        errors.append(
            f"Streamlit 1.56.0 is required; found {streamlit or 'not installed'}."
        )

    if requests is None or not ((2, 32, 0) <= _version_tuple(requests) < (3, 0, 0)):
        errors.append(
            f"requests >=2.32,<3 is required; found {requests or 'not installed'}."
        )

    if dotenv is None or not ((1, 0, 0) <= _version_tuple(dotenv) < (2, 0, 0)):
        errors.append(
            f"python-dotenv >=1.0,<2 is required; found {dotenv or 'not installed'}."
        )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Daybook AI host-environment preflight")
    parser.add_argument(
        "--verify-deps",
        action="store_true",
        help="Also verify packages declared by requirements.txt.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only emit errors and warnings.",
    )
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    version = sys.version_info
    if (version.major, version.minor) != SUPPORTED_PYTHON:
        errors.append(
            "This Daybook AI installer uses CPython 3.12.x as the validated runtime; "
            f"found {platform.python_version()}."
        )
    else:
        info.append(f"Python: {platform.python_version()} ({sys.executable})")

    required_files = ("run.py", "app.py", "requirements.txt", ".env.example")
    for name in required_files:
        if not (PROJECT_ROOT / name).exists():
            errors.append(f"Required project file is missing: {name}")

    try:
        usage = shutil.disk_usage(PROJECT_ROOT)
        free_gib = usage.free / (1024 ** 3)
        info.append(f"Free disk space: {free_gib:.1f} GiB")
        if free_gib < RECOMMENDED_FREE_DISK_GIB:
            warnings.append(
                f"Only {free_gib:.1f} GiB is free. At least "
                f"{RECOMMENDED_FREE_DISK_GIB:.0f} GiB free is recommended for "
                "the virtual environment, llama.cpp runtime, model, and application data."
            )
    except OSError as exc:
        warnings.append(f"Free disk space could not be determined: {exc}")

    ram_bytes = _total_ram_bytes()
    if ram_bytes is not None:
        ram_gib = ram_bytes / (1024 ** 3)
        info.append(f"System RAM: {ram_gib:.1f} GiB")
        if ram_gib < RECOMMENDED_RAM_GIB:
            warnings.append(
                f"Only {ram_gib:.1f} GiB RAM was detected. "
                f"{RECOMMENDED_RAM_GIB:.0f} GiB or more is recommended."
            )
    else:
        warnings.append("System RAM could not be determined.")

    try:
        import sqlite3  # noqa: F401
        import ssl  # noqa: F401
        info.append("Python standard-library checks: SQLite and SSL available")
    except ImportError as exc:
        errors.append(f"Required Python standard-library component is unavailable: {exc}")

    try:
        from src.runtime.hardware import detect_hardware

        hardware = detect_hardware()
        info.append(
            "Hardware: "
            f"{hardware.operating_system} {hardware.architecture}; "
            f"compute={hardware.gpu_name or 'CPU only'}; "
            f"recommended backend={hardware.recommended_backend}"
        )
    except Exception as exc:  # preflight should report, not crash, on hardware probing
        warnings.append(f"Hardware acceleration could not be classified: {exc}")

    expected_venv = PROJECT_ROOT / ".venv"
    try:
        in_project_venv = Path(sys.prefix).resolve() == expected_venv.resolve()
    except OSError:
        in_project_venv = False
    if in_project_venv:
        info.append("Virtual environment: project .venv")
    else:
        warnings.append(
            "Preflight is not running from the project .venv. The installer should invoke "
            "this script with .venv's Python interpreter."
        )

    if args.verify_deps:
        dependency_errors = _verify_dependencies()
        errors.extend(dependency_errors)
        if not dependency_errors:
            info.append("Python dependencies: requirements.txt constraints satisfied")

    if not args.quiet:
        print("Daybook AI environment preflight")
        print("-" * 34)
        for line in info:
            print(f"OK   {line}")

    for line in warnings:
        print(f"WARN {line}")
    for line in errors:
        print(f"ERROR {line}")

    if not args.quiet:
        if errors:
            print("\nPreflight failed.")
        else:
            print("\nPreflight passed.")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
