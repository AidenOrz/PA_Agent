"""Integration test: stage 1 raises a network timeout error.

Task 11.9
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import openai
import pytest

from tests.fixtures.validators import schema_test_validator
from pa_agent.ai.router import route_strategy_files
from pa_agent.config.settings import Settings
from pa_agent.orchestrator.two_stage import TwoStageOrchestrator
from pa_agent.util.threading import CancelToken, OrchestratorEvent

from .conftest import make_reply


def test_httpx_read_error_stage1(frame, pending_writer, assembler, exp_reader):
    """httpx.ReadError (e.g. WinError 10054 mid-stream) → Stage1Failed + partial save."""
    try:
        import httpx
    except ImportError:
        return

    client = MagicMock()
    client.stream_chat.side_effect = httpx.ReadError(
        "[WinError 10054] 远程主机强迫关闭了一个现有的连接。"
    )

    validator = schema_test_validator()
    orchestrator = TwoStageOrchestrator(
        client=client,
        assembler=assembler,
        router=route_strategy_files,
        validator=validator,
        pending_writer=pending_writer,
        exp_reader=exp_reader,
    )

    events: list[OrchestratorEvent] = []
    orchestrator.submit(
        frame=frame,
        cancel_token=CancelToken(),
        on_event=events.append,
    )

    assert OrchestratorEvent.Stage1Failed in events
    pending_writer.save_partial.assert_called_once()
    assert pending_writer.save_partial.call_args[0][1] == "network_error"


def test_network_timeout_stage1(frame, pending_writer, assembler, exp_reader):
    """APITimeoutError on stage1 → Stage1Failed emitted."""
    client = MagicMock()
    # openai.APITimeoutError requires a `request` parameter
    client.stream_chat.side_effect = openai.APITimeoutError(request=MagicMock())

    validator = schema_test_validator()
    orchestrator = TwoStageOrchestrator(
        client=client,
        assembler=assembler,
        router=route_strategy_files,
        validator=validator,
        pending_writer=pending_writer,
        exp_reader=exp_reader,
    )

    events: list[OrchestratorEvent] = []
    cancel_token = CancelToken()

    orchestrator.submit(
        frame=frame,
        cancel_token=cancel_token,
        on_event=events.append,
    )

    # Stage1Failed event must appear
    assert OrchestratorEvent.Stage1Failed in events

    # Stage2 must never start
    assert OrchestratorEvent.Stage2Started not in events

    # save_partial called with reason "network_error"
    pending_writer.save_partial.assert_called_once()
    call_args = pending_writer.save_partial.call_args
    reason = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("reason", "")
    assert reason == "network_error"


@pytest.mark.parametrize("status_code", [400, 401, 403, 429])
def test_client_4xx_does_not_trigger_network_fallback(status_code: int):
    """Client/credential errors must not be retried through another provider."""
    import httpx

    response = httpx.Response(
        status_code,
        request=httpx.Request("POST", "https://provider.test/v1/chat/completions"),
    )
    error = openai.APIStatusError(
        f"provider returned HTTP {status_code}",
        response=response,
        body=None,
    )
    assert not TwoStageOrchestrator._is_network_error(error)


def test_retry_api_error_saves_stage1_partial(
    frame, pending_writer, assembler, exp_reader,
):
    """A failed validation retry is persisted with retry messages and stage info."""
    try:
        import httpx
    except ImportError:
        return

    client = MagicMock()
    client.stream_chat.side_effect = [
        make_reply({"gate_result": "proceed"}),
        httpx.ReadError("retry connection dropped"),
    ]
    orchestrator = TwoStageOrchestrator(
        client=client,
        assembler=assembler,
        router=route_strategy_files,
        validator=schema_test_validator(),
        pending_writer=pending_writer,
        exp_reader=exp_reader,
    )

    events: list[OrchestratorEvent] = []
    record = orchestrator.submit(
        frame=frame,
        cancel_token=CancelToken(),
        on_event=events.append,
    )

    assert OrchestratorEvent.Stage1Failed in events
    pending_writer.save_partial.assert_called_once()
    partial = pending_writer.save_partial.call_args.args[0]
    assert partial is record
    assert partial.stage1_response is not None
    assert partial.exception["stage"] == "stage1"
    assert partial.exception["type"] == "network_error"
    assert partial.usage_total["prompt_tokens"] == 100
    assert len(partial.stage1_messages) >= 3


def test_qclaw_fallback_is_temporary_and_does_not_save_settings(
    assembler, pending_writer, exp_reader,
):
    settings = Settings()
    settings.provider.model = "openclaw"
    settings.provider.base_url = "https://original.test/v1"
    client = MagicMock()
    orchestrator = TwoStageOrchestrator(
        client=client,
        assembler=assembler,
        router=route_strategy_files,
        validator=schema_test_validator(),
        pending_writer=pending_writer,
        exp_reader=exp_reader,
        settings=settings,
    )

    def apply_fallback(temp_settings):
        temp_settings.provider.model = "qclaw-fallback"
        temp_settings.provider.base_url = "http://127.0.0.1:19000/v1"
        return None

    with patch("pa_agent.ai.qclaw_connector.is_openclaw_model", return_value=True):
        with patch(
            "pa_agent.ai.qclaw_connector.apply_qclaw_provider_to_settings",
            side_effect=apply_fallback,
        ):
            with patch("pa_agent.config.settings.save_settings") as save_settings:
                assert orchestrator._try_qclaw_fallback(original_model="openclaw")

    assert settings.provider.model == "openclaw"
    assert settings.provider.base_url == "https://original.test/v1"
    save_settings.assert_not_called()
    fallback_provider = client.update_provider.call_args.args[0]
    assert fallback_provider is not settings.provider
    assert fallback_provider.model == "qclaw-fallback"
