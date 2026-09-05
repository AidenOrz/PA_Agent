"""Regression tests for WorkBuddy authentication failures."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pa_agent.ai.workbuddy_connector import _probe_workbuddy_api


@pytest.mark.parametrize("status_code", [401, 403])
def test_workbuddy_probe_rejects_authentication_failures(status_code: int) -> None:
    try:
        import httpx  # noqa: F401
    except ImportError:
        pytest.skip("httpx is not installed")

    response = MagicMock()
    response.status_code = status_code
    stream_context = MagicMock()
    stream_context.__enter__.return_value = response

    with patch("httpx.stream", return_value=stream_context):
        assert not _probe_workbuddy_api(
            "https://workbuddy.test/v1", "token", timeout=0.1
        )
