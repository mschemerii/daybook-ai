from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from src.runtime.controller import ControllerConfig, ControllerServer


def test_controller_health_and_shutdown():
    controller = ControllerServer(
        ControllerConfig(
            host="127.0.0.1",
            port=0,
            streamlit_url="http://127.0.0.1:8501",
            shutdown_token="test-token",
        )
    )
    controller.start()
    try:
        port = controller._server.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
            assert response.read() == b"ok"

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/shutdown?token=test-token",
            timeout=2,
        ) as response:
            body = response.read().decode("utf-8")
            assert "has shut down" in body

        assert controller.wait_for_shutdown(timeout=1)
    finally:
        controller.stop()


def test_controller_rejects_unauthenticated_shutdown():
    controller = ControllerServer(
        ControllerConfig(
            host="127.0.0.1",
            port=0,
            streamlit_url="http://127.0.0.1:8501",
            shutdown_token="test-token",
        )
    )
    controller.start()
    try:
        port = controller._server.server_address[1]
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/shutdown", timeout=2)
        assert error.value.code == 403
        assert not controller.wait_for_shutdown(timeout=0.05)
    finally:
        controller.stop()
