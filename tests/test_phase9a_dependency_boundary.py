from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_phase9a_adds_pyside6_without_removing_streamlit() -> None:
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()

    assert any(line.startswith("PySide6>=") for line in requirements)
    assert "streamlit==1.56.0" in requirements


def test_desktop_runtime_has_no_browser_or_streamlit_startup_path() -> None:
    source = (PROJECT_ROOT / "src/desktop/runtime.py").read_text(encoding="utf-8").lower()

    assert "import streamlit" not in source
    assert "_start_streamlit" not in source
    assert "webbrowser" not in source
    assert "controllerserver" not in source
    assert "_run_qt_application" in source


def test_desktop_composition_uses_existing_application_layers_directly() -> None:
    source = (PROJECT_ROOT / "src/desktop/composition.py").read_text(encoding="utf-8")

    expected_imports = (
        "src.repositories.database",
        "src.repositories.task_repository",
        "src.repositories.journal_repository",
        "src.services.task_service",
        "src.services.context_service",
        "src.services.planning_service",
        "src.services.reporting_service",
    )
    for module in expected_imports:
        assert module in source
    assert "streamlit" not in source.lower()
