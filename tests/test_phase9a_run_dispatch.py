from __future__ import annotations

import runpy
import sys
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_root_launcher_dispatches_desktop_by_default_without_loading_streamlit_runtime(monkeypatch) -> None:
    fake_desktop_runtime = ModuleType("src.desktop.runtime")
    fake_desktop_runtime.run = lambda: 17  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "src.desktop.runtime", fake_desktop_runtime)
    monkeypatch.delitem(sys.modules, "src.runtime.launcher", raising=False)
    monkeypatch.setattr(sys, "argv", ["run.py"])

    namespace = runpy.run_path(str(PROJECT_ROOT / "run.py"), run_name="daybook_run_test")

    assert namespace["main"]() == 17
    assert "src.runtime.launcher" not in sys.modules


def test_root_launcher_rejects_extra_desktop_options(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["run.py", "--desktop", "--status"])
    namespace = runpy.run_path(str(PROJECT_ROOT / "run.py"), run_name="daybook_run_test")

    assert namespace["main"]() == 2
    assert "does not accept additional launcher options" in capsys.readouterr().err


def test_root_launcher_preserves_explicit_desktop_alias(monkeypatch) -> None:
    fake_desktop_runtime = ModuleType("src.desktop.runtime")
    fake_desktop_runtime.run = lambda: 18  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "src.desktop.runtime", fake_desktop_runtime)
    monkeypatch.setattr(sys, "argv", ["run.py", "--desktop"])
    namespace = runpy.run_path(str(PROJECT_ROOT / "run.py"), run_name="daybook_run_test")

    assert namespace["main"]() == 18


def test_root_launcher_runs_streamlit_only_when_explicit(monkeypatch) -> None:
    received: list[list[str]] = []
    fake_legacy_runtime = ModuleType("src.runtime.launcher")

    def fake_run() -> int:
        received.append(sys.argv[1:])
        return 19

    fake_legacy_runtime.run = fake_run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "src.runtime.launcher", fake_legacy_runtime)
    monkeypatch.delitem(sys.modules, "src.desktop.runtime", raising=False)
    monkeypatch.setattr(sys, "argv", ["run.py", "--streamlit"])
    namespace = runpy.run_path(str(PROJECT_ROOT / "run.py"), run_name="daybook_run_test")

    assert namespace["main"]() == 19
    assert received == [[]]
    assert "src.desktop.runtime" not in sys.modules


def test_root_launcher_preserves_legacy_management_options(monkeypatch) -> None:
    received: list[list[str]] = []
    fake_legacy_runtime = ModuleType("src.runtime.launcher")
    fake_legacy_runtime.run = lambda: received.append(sys.argv[1:]) or 20  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "src.runtime.launcher", fake_legacy_runtime)
    monkeypatch.setattr(sys, "argv", ["run.py", "--status"])
    namespace = runpy.run_path(str(PROJECT_ROOT / "run.py"), run_name="daybook_run_test")

    assert namespace["main"]() == 20
    assert received == [["--status"]]
