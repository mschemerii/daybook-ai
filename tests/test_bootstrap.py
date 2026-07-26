from pathlib import Path

from src.runtime.bootstrap import choose_llama_asset, find_existing_model
from src.runtime.hardware import HardwareInfo


def hardware(system: str, arch: str, vendor: str | None) -> HardwareInfo:
    return HardwareInfo(system, arch, vendor, vendor, "test", vendor is not None, "test")


def test_selects_windows_cuda_for_nvidia():
    assets = [
        {"name": "llama-b9000-bin-win-cpu-x64.zip"},
        {"name": "llama-b9000-bin-win-cuda-12.4-x64.zip"},
        {"name": "cudart-llama-bin-win-cuda-12.4-x64.zip"},
    ]
    selected = choose_llama_asset(assets, hardware("Windows", "AMD64", "NVIDIA"))
    assert selected is not None
    assert "cuda" in str(selected["name"]).lower()
    assert "cudart" not in str(selected["name"]).lower()


def test_selects_linux_cpu_fallback():
    assets = [
        {"name": "llama-b9000-bin-ubuntu-x64.tar.gz"},
        {"name": "llama-b9000-bin-win-cpu-x64.zip"},
    ]
    selected = choose_llama_asset(assets, hardware("Linux", "x86_64", None))
    assert selected is not None
    assert "ubuntu" in str(selected["name"]).lower()


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
