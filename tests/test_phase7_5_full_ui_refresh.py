from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = PROJECT_ROOT / "app.py"


def test_phase7_5_full_ui_refresh_is_present() -> None:
    app_source = APP_FILE.read_text(encoding="utf-8")

    assert 'key="today_summary_metrics"' in app_source
    assert 'key="today_workspace"' in app_source
    assert 'st.tabs(["Due today", "Blockers"])' in app_source
    assert 'key="task_index_grid"' in app_source
    assert 'key="journal_workspace"' in app_source
    assert 'key="assistant_workspace"' in app_source
    assert 'st.tabs(["Memory", "Audit"])' in app_source
    assert 'key="about_workspace"' in app_source
    assert 'key="ethical_workspace"' in app_source
    assert '"NIST AI RMF alignment"' in app_source
    assert 'Rules determine · AI explains/proposes · You approve' in app_source
