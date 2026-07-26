from pathlib import Path
from types import SimpleNamespace

from src.runtime import launcher


def test_version_tuple_handles_release_versions():
    assert launcher._version_tuple("1.56.0") == (1, 56, 0)
    assert launcher._version_tuple("1.57.0rc1") == (1, 57, 1)


def test_compatible_streamlit_does_not_reinstall(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(launcher.metadata, "version", lambda _: "1.56.0")

    def fail_run(*args, **kwargs):
        raise AssertionError("pip should not run for a compatible version")

    monkeypatch.setattr(launcher.subprocess, "run", fail_run)
    assert launcher._ensure_compatible_streamlit(tmp_path) is True


def test_incompatible_streamlit_is_replaced(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(launcher.metadata, "version", lambda _: "1.57.0")
    calls = []

    def fake_run(command, cwd, check):
        calls.append((command, cwd, check))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(launcher.subprocess, "run", fake_run)
    assert launcher._ensure_compatible_streamlit(tmp_path) is True
    assert launcher.STREAMLIT_COMPAT_SPEC in calls[0][0]
