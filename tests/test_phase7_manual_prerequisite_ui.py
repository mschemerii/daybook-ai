from pathlib import Path


APP_FILE = Path(__file__).resolve().parents[1] / "app.py"


def test_manual_review_item_can_select_prerequisites_before_insert() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert '"Manual task prerequisites"' in source
    assert 'manual_prerequisite_keys = st.multiselect(' in source
    assert "planning_service.set_review_prerequisites(" in source
    assert "manual_item.item_key" in source
