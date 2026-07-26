from __future__ import annotations

import os
from pathlib import Path

import pytest

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_FILE = PROJECT_ROOT / "app.py"


@pytest.fixture
def app_test(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Run the Streamlit application with an isolated SQLite database."""
    monkeypatch.setenv(
        "DAYBOOK_DB_PATH",
        str(tmp_path / "daybook-ui-test.db"),
    )
    monkeypatch.setenv(
        "DAYBOOK_MODEL_BASE_URL",
        "http://127.0.0.1:1/v1",
    )
    monkeypatch.setenv(
        "DAYBOOK_CONTROLLER_URL",
        "http://127.0.0.1:8500",
    )

    app = AppTest.from_file(str(APP_FILE))
    app.run(timeout=30)

    return app


@pytest.mark.streamlit
def test_application_loads_without_exception(app_test):
    assert not app_test.exception


@pytest.mark.streamlit
def test_today_page_is_default(app_test):
    assert any(
        title.value == "Today"
        for title in app_test.title
    )


@pytest.mark.streamlit
def test_primary_navigation_is_available(app_test):
    assert app_test.radio

    navigation = app_test.radio[0]

    assert list(navigation.options) == [
        "Today",
        "Tasks",
        "Daily Journal",
        "Assistant",
        "About",
        "Ethical AI",
    ]


@pytest.mark.streamlit
def test_tasks_page_opens(app_test):
    navigation = app_test.radio[0]
    navigation.set_value("Tasks")
    app_test.run(timeout=30)

    assert not app_test.exception
    assert any(
        title.value == "Tasks"
        for title in app_test.title
    )


@pytest.mark.streamlit
def test_about_page_opens(app_test):
    navigation = app_test.radio[0]
    navigation.set_value("About")
    app_test.run(timeout=30)

    assert not app_test.exception
    assert any(
        title.value == "About Daybook AI"
        for title in app_test.title
    )


@pytest.mark.streamlit
def test_ethical_ai_page_opens(app_test):
    navigation = app_test.radio[0]
    navigation.set_value("Ethical AI")
    app_test.run(timeout=30)

    assert not app_test.exception
    assert any(
        title.value == "Ethical AI"
        for title in app_test.title
    )
