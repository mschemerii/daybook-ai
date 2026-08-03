import io
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from src.runtime import bootstrap
from src.runtime.bootstrap import (
    ExecutableValidationError,
    LlamaInspection,
    LlamaPackage,
    _download,
    _matches_pinned_release,
    _package_for_hardware,
    _read_compatible_manifest,
    _safe_extract_zip,
    choose_llama_asset,
    find_existing_model,
    inspect_llama_server,
    install_llama_cpp,
)
from src.runtime.hardware import HardwareInfo


def hardware(system: str, arch: str, vendor: str | None) -> HardwareInfo:
    return HardwareInfo(system, arch, vendor, vendor, "test", vendor is not None, "test")


@pytest.mark.parametrize(
    ("system", "arch", "vendor", "backend", "asset_fragment"),
    [
        ("Darwin", "arm64", "Apple", "Metal", "macos-arm64"),
        ("Darwin", "x86_64", "Intel", "Metal", "macos-x64"),
        ("Windows", "AMD64", "NVIDIA", "CUDA", "win-cuda-12.4-x64"),
        ("Windows", "AMD64", "AMD", "HIP", "win-hip-radeon-x64"),
        ("Windows", "AMD64", "Intel", "SYCL", "win-sycl-x64"),
        ("Windows", "AMD64", None, "CPU", "win-cpu-x64"),
        ("Windows", "ARM64", None, "CPU", "win-cpu-arm64"),
        ("Linux", "x86_64", "NVIDIA", "Vulkan", "ubuntu-vulkan-x64"),
        ("Linux", "x86_64", "AMD", "ROCm", "ubuntu-rocm-7.2-x64"),
        ("Linux", "x86_64", "Intel", "Vulkan", "ubuntu-vulkan-x64"),
        ("Linux", "x86_64", None, "CPU", "ubuntu-x64"),
        ("Linux", "aarch64", None, "CPU", "ubuntu-arm64"),
    ],
)
def test_platform_matrix_is_explicit(system, arch, vendor, backend, asset_fragment):
    package = _package_for_hardware(hardware(system, arch, vendor))
    assert package is not None
    assert package.backend == backend
    assert asset_fragment in package.asset_names[0]


def test_windows_cuda_includes_official_runtime_dependency():
    package = _package_for_hardware(hardware("Windows", "AMD64", "NVIDIA"))
    assert package is not None
    assert len(package.asset_names) == 2
    assert package.asset_names[1].startswith("cudart-")


def test_asset_selection_does_not_use_fuzzy_backend_scoring():
    assets = [
        {"name": "llama-b9000-bin-win-openvino-x64.zip"},
        {"name": "llama-b9000-bin-win-cuda-12.4-x64.zip"},
        {"name": "cudart-llama-bin-win-cuda-12.4-x64.zip"},
    ]
    selected = choose_llama_asset(assets, hardware("Windows", "AMD64", "NVIDIA"))
    assert selected is not None
    assert selected["name"] == "llama-b9000-bin-win-cuda-12.4-x64.zip"


def test_unsupported_platform_has_no_package():
    assert _package_for_hardware(hardware("FreeBSD", "x86_64", None)) is None


def test_pinned_version_output_must_include_expected_build_number():
    assert _matches_pinned_release("version: 10217 (abc123)")
    assert not _matches_pinned_release("version: 10216 (abc123)")
    assert not _matches_pinned_release("version: 110217 (abc123)")


def test_configured_executable_takes_precedence(tmp_path: Path, monkeypatch):
    configured = tmp_path / "custom-llama-server"
    configured.write_bytes(b"binary")
    monkeypatch.setenv("DAYBOOK_LLAMA_SERVER", str(configured))

    expected = LlamaInspection(configured.resolve(), "b10000", "Metal0", "Metal", 99)
    monkeypatch.setattr(
        bootstrap,
        "inspect_llama_server",
        lambda path, backend, compatible_backends=(): expected,
    )
    monkeypatch.setattr(
        bootstrap,
        "_install_pinned_package",
        lambda *args, **kwargs: pytest.fail("automatic install must not run"),
    )

    assert install_llama_cpp(tmp_path, hardware("Darwin", "arm64", "Apple")) == expected


def test_sibling_executable_is_not_reused(tmp_path: Path, monkeypatch):
    project = tmp_path / "daybook-ai-current"
    project.mkdir()
    sibling = tmp_path / "daybook-ai-old" / "tools" / "llama.cpp" / "llama-server"
    sibling.parent.mkdir(parents=True)
    sibling.write_bytes(b"untrusted")
    monkeypatch.delenv("DAYBOOK_LLAMA_SERVER", raising=False)
    monkeypatch.setattr(bootstrap.shutil, "which", lambda _: None)

    expected = LlamaInspection(project / "validated", "b10217", "", "CPU", 0)
    monkeypatch.setattr(bootstrap, "_install_pinned_package", lambda *args, **kwargs: expected)

    assert install_llama_cpp(project, hardware("Linux", "x86_64", None)) == expected


def test_failed_accelerated_executable_uses_generic_cpu_package(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DAYBOOK_LLAMA_SERVER", raising=False)
    monkeypatch.setattr(bootstrap.shutil, "which", lambda _: None)
    attempted_backends = []
    expected = LlamaInspection(tmp_path / "cpu-server", "b10217", "", "CPU", 0)

    def fake_install(project_root, detected_hardware, package, reporter):
        attempted_backends.append(package.backend)
        if package.backend == "Vulkan":
            raise ExecutableValidationError("driver unavailable")
        return expected

    monkeypatch.setattr(bootstrap, "_install_pinned_package", fake_install)

    result = install_llama_cpp(tmp_path, hardware("Linux", "x86_64", "NVIDIA"))

    assert result == expected
    assert attempted_backends == ["Vulkan", "CPU"]


class FakeResponse(io.BytesIO):
    def __init__(self, payload: bytes):
        super().__init__(payload)
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_download_rejects_sha256_mismatch(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        bootstrap.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(b"payload"),
    )
    destination = tmp_path / "archive.zip"

    with pytest.raises(RuntimeError, match="SHA-256 verification failed"):
        _download("https://example.invalid/archive.zip", destination, "archive", expected_sha256="0" * 64)

    assert not destination.exists()
    assert not destination.with_suffix(".zip.part").exists()


def test_zip_extraction_rejects_path_traversal(tmp_path: Path):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../escape", "unsafe")

    with pytest.raises(ValueError, match="Unsafe path"):
        _safe_extract_zip(archive, tmp_path / "extract")


def test_manifest_rejects_modified_executable(tmp_path: Path):
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    executable = install_dir / "llama-server"
    executable.write_bytes(b"original")
    package = LlamaPackage("CPU", ("llama-b10217-bin-ubuntu-x64.tar.gz",))
    manifest = {
        "release": "b10217",
        "assets": list(package.asset_names),
        "operating_system": "Linux",
        "architecture": "x64",
        "backend": "CPU",
        "executable": "llama-server",
        "executable_sha256": bootstrap._sha256_file(executable),
    }
    (install_dir / "install-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    executable.write_bytes(b"modified")

    result = _read_compatible_manifest(
        install_dir,
        hardware("Linux", "x86_64", None),
        package,
    )
    assert result is None


def test_inspection_enables_gpu_layers_only_when_backend_is_visible(tmp_path: Path, monkeypatch):
    executable = tmp_path / "llama-server"
    executable.write_bytes(b"binary")
    results = iter(
        [
            subprocess.CompletedProcess([], 0, stdout="version: b10217", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="CUDA0: NVIDIA RTX 3090", stderr=""),
        ]
    )
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *args, **kwargs: next(results))

    inspection = inspect_llama_server(executable, "CUDA")
    assert inspection is not None
    assert inspection.backend == "CUDA"
    assert inspection.gpu_layers == 99


def test_inspection_recognizes_current_llama_cpp_metal_device_label(tmp_path: Path, monkeypatch):
    executable = tmp_path / "llama-server"
    executable.write_bytes(b"binary")
    results = iter(
        [
            subprocess.CompletedProcess([], 0, stdout="version: 10200", stderr=""),
            subprocess.CompletedProcess(
                [],
                0,
                stdout=(
                    "Available devices:\n"
                    "  BLAS: Accelerate (0 MiB, 0 MiB free)\n"
                    "  MTL0: Apple M4 Max (110100 MiB, 110100 MiB free)"
                ),
                stderr="",
            ),
        ]
    )
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *args, **kwargs: next(results))

    inspection = inspect_llama_server(executable, "Metal")

    assert inspection is not None
    assert inspection.backend == "Metal"
    assert inspection.gpu_layers == 99


def test_inspection_falls_back_to_cpu_when_backend_is_missing(tmp_path: Path, monkeypatch):
    executable = tmp_path / "llama-server"
    executable.write_bytes(b"binary")
    results = iter(
        [
            subprocess.CompletedProcess([], 0, stdout="version: b10217", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="Available devices:", stderr=""),
        ]
    )
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *args, **kwargs: next(results))

    inspection = inspect_llama_server(executable, "CUDA")
    assert inspection is not None
    assert inspection.backend == "CPU"
    assert inspection.gpu_layers == 0


def test_configured_linux_cuda_backend_is_accepted(tmp_path: Path, monkeypatch):
    executable = tmp_path / "llama-server"
    executable.write_bytes(b"binary")
    results = iter(
        [
            subprocess.CompletedProcess([], 0, stdout="version: custom", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="CUDA0: NVIDIA RTX 3090", stderr=""),
        ]
    )
    monkeypatch.setattr(
        bootstrap.subprocess,
        "run",
        lambda *args, **kwargs: next(results),
    )

    inspection = inspect_llama_server(
        executable,
        "Vulkan",
        compatible_backends=("CUDA", "Vulkan"),
    )

    assert inspection is not None
    assert inspection.backend == "CUDA"
    assert inspection.gpu_layers == 99


def test_existing_gguf_is_not_replaced(tmp_path: Path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    existing = models / "custom.gguf"
    existing.write_bytes(b"model")
    monkeypatch.delenv("DAYBOOK_MODEL_PATH", raising=False)
    assert find_existing_model(tmp_path) == existing.resolve()


def test_existing_gguf_is_found_recursively(tmp_path: Path, monkeypatch):
    nested = tmp_path / "models" / "nested"
    nested.mkdir(parents=True)
    existing = nested / "Qwen3.5-0.8B-test.gguf"
    existing.write_bytes(b"model")
    monkeypatch.delenv("DAYBOOK_MODEL_PATH", raising=False)
    assert find_existing_model(tmp_path) == existing.resolve()


def test_existing_gguf_is_reused_from_sibling_project(tmp_path: Path, monkeypatch):
    current = tmp_path / "daybook-ai-production"
    current.mkdir()
    sibling_models = tmp_path / "daybook-ai-old" / "models"
    sibling_models.mkdir(parents=True)
    existing = sibling_models / "Qwen3.5-0.8B-test.gguf"
    existing.write_bytes(b"model")
    monkeypatch.delenv("DAYBOOK_MODEL_PATH", raising=False)
    assert find_existing_model(current) == existing.resolve()
