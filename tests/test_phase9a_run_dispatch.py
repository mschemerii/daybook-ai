from __future__ import annotations

import runpy
import sys
from pathlib import Path
from types import ModuleType


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_root_launcher_dispatches_desktop_without_loading_streamlit_runtime(monkeypatch) -> None:
    fake_desktop_runtime = ModuleType("src.desktop.runtime")
    fake_desktop_runtime.run = lambda: 17  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "src.desktop.runtime", fake_desktop_runtime)
    monkeypatch.delitem(sys.modules, "src.runtime.launcher", raising=False)
    monkeypatch.setattr(sys, "argv", ["run.py", "--desktop"])

    namespace = runpy.run_path(str(PROJECT_ROOT / "run.py"), run_name="daybook_run_test")

    assert namespace["main"]() == 17
    assert "src.runtime.launcher" not in sys.modules


def test_root_launcher_rejects_extra_desktop_options(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["run.py", "--desktop", "--status"])
    namespace = runpy.run_path(str(PROJECT_ROOT / "run.py"), run_name="daybook_run_test")

    assert namespace["main"]() == 2
    assert "does not accept additional launcher options" in capsys.readouterr().err


def test_root_launcher_keeps_streamlit_runtime_as_phase9a_default() -> None:
    source = (PROJECT_ROOT / "run.py").read_text(encoding="utf-8")

    assert 'if "--desktop" in sys.argv[1:]' in source
    assert "from src.runtime.launcher import run as run_streamlit" in source
    assert "return run_streamlit()" in source
