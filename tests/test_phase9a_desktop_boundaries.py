from __future__ import annotations

from pathlib import Path


def test_desktop_package_has_no_streamlit_dependency() -> None:
    project_root = Path(__file__).resolve().parents[1]
    desktop_root = project_root / "src" / "desktop"

    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(desktop_root.glob("*.py"))
    ).lower()

    assert "import streamlit" not in source
    assert "from streamlit" not in source
    assert "session_state" not in source
    assert "webbrowser" not in source
