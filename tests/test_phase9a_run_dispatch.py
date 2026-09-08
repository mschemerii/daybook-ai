from __future__ import annotations

import runpy
import sys
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _namespace(monkeypatch):
    return runpy.run_path(str(PROJECT_ROOT / "run.py"), run_name="daybook_run_test")


def test_root_launcher_dispatches_desktop_by_default(monkeypatch) -> None:
    fake_desktop_runtime = ModuleType("src.desktop.runtime")
    fake_desktop_runtime.run = lambda: 17  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "src.desktop.runtime", fake_desktop_runtime)
    monkeypatch.setattr(sys, "argv", ["run.py"])

    namespace = _namespace(monkeypatch)

    assert namespace["main"]() == 17


def test_root_launcher_rejects_extra_desktop_options(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["run.py", "--desktop", "--status"])
    namespace = _namespace(monkeypatch)

    assert namespace["main"]() == 2
    assert "does not accept additional launcher options" in capsys.readouterr().err


def test_root_launcher_preserves_explicit_desktop_alias(monkeypatch) -> None:
    fake_desktop_runtime = ModuleType("src.desktop.runtime")
    fake_desktop_runtime.run = lambda: 18  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "src.desktop.runtime", fake_desktop_runtime)
    monkeypatch.setattr(sys, "argv", ["run.py", "--desktop"])
    namespace = _namespace(monkeypatch)

    assert namespace["main"]() == 18


def test_root_launcher_rejects_removed_legacy_modes(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["run.py", "--streamlit"])
    namespace = _namespace(monkeypatch)

    assert namespace["main"]() == 2
    assert "Unknown launcher option" in capsys.readouterr().err
