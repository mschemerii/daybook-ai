from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.runtime.preferences import (
    DEFAULT_APPEARANCE,
    load_appearance_preference,
    save_appearance_preference,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = PROJECT_ROOT / "app.py"
CAPTURE_FILE = PROJECT_ROOT / "scripts" / "capture_pages.py"


def test_phase7_5_appearance_switch_is_present() -> None:
    app_source = APP_FILE.read_text(encoding="utf-8")

    assert 'if "appearance_mode" not in st.session_state:' in app_source
    assert "load_appearance_preference(PREFERENCES_PATH)" in app_source
    assert "save_appearance_preference(" in app_source
    assert "on_change=_persist_appearance_mode" in app_source
    assert 'st.query_params.get("daybook_capture") == "1"' in app_source
    assert 'key="sidebar_appearance"' in app_source
    assert '["Light", "Dark"]' in app_source
    assert 'data-daybook-theme="{appearance_key}"' in app_source
    assert 'bottom: 5.7rem;' in app_source
    assert 'padding-bottom: 10.5rem;' in app_source
    assert "# phase7-5-light-dark-component-contrast" in app_source
    assert "component_surface =" in app_source
    assert '.stApp [data-testid="stButton"] button' in app_source
    assert '[data-testid="stSidebar"] [role="radiogroup"] label' in app_source


def test_capture_pages_uses_app_appearance_switch() -> None:
    capture_source = CAPTURE_FILE.read_text(encoding="utf-8")

    assert 'default="both"' in capture_source
    assert "def set_appearance(page: Page, theme: str)" in capture_source
    assert "set_appearance(page, theme)" in capture_source
    assert 'data-daybook-theme="{theme}"' in capture_source
    assert 'name="Open task"' in capture_source
    assert "exact=True" in capture_source
    assert "def url_ready(url: str" in capture_source
    assert "def capture_url(url: str) -> str:" in capture_source
    assert "daybook_capture=1" in capture_source
    assert "def run_managed_capture(theme: str) -> int:" in capture_source
    assert 'MANAGED_CAPTURE_ENV = "DAYBOOK_CAPTURE_MANAGED"' in capture_source
    assert "controller_ready != streamlit_ready" in capture_source
    assert '"--screenshots",' in capture_source


def test_appearance_preference_defaults_to_light(tmp_path: Path) -> None:
    preference_path = tmp_path / ".daybook-preferences.json"
    assert load_appearance_preference(preference_path) == DEFAULT_APPEARANCE


def test_appearance_preference_round_trip(tmp_path: Path) -> None:
    preference_path = tmp_path / ".daybook-preferences.json"
    save_appearance_preference(preference_path, "Dark")

    assert load_appearance_preference(preference_path) == "Dark"
    assert json.loads(preference_path.read_text(encoding="utf-8")) == {
        "appearance": "Dark"
    }


def test_invalid_or_corrupt_appearance_falls_back_to_light(
    tmp_path: Path,
) -> None:
    preference_path = tmp_path / ".daybook-preferences.json"
    preference_path.write_text(
        '{"appearance": "Sepia"}',
        encoding="utf-8",
    )
    assert load_appearance_preference(preference_path) == DEFAULT_APPEARANCE

    preference_path.write_text("{not-json", encoding="utf-8")
    assert load_appearance_preference(preference_path) == DEFAULT_APPEARANCE


def test_appearance_preference_rejects_unknown_value(tmp_path: Path) -> None:
    preference_path = tmp_path / ".daybook-preferences.json"
    with pytest.raises(ValueError):
        save_appearance_preference(preference_path, "Sepia")
