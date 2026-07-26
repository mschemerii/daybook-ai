from __future__ import annotations

import pytest
from playwright.sync_api import FrameLocator


@pytest.mark.ui
def test_primary_navigation_has_accessible_name(
    app_frame: FrameLocator,
):
    navigation = app_frame.get_by_role(
        "radiogroup",
        name="Primary navigation",
    )

    assert navigation.count() == 1


@pytest.mark.ui
def test_shutdown_control_has_accessible_name(
    app_frame: FrameLocator,
):
    shutdown = app_frame.get_by_role(
        "link",
        name="Shut down Daybook AI",
    )

    assert shutdown.count() == 1
