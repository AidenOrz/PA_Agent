"""Unit tests for DeepSeekClient (task 6.5)."""
from __future__ import annotations

import sys
import pytest
from unittest.mock import MagicMock, patch, call
from pa_agent.config.settings import AIProviderSettings
from pa_agent.ai.deepseek_client import (
    DeepSeekClient,
    AIReply,
    AIUsage,
    CancelledError,
    _completion_max_tokens,
    _is_deepseek_model,
    _openclaw_agent_request_extra,
    _is_stream_options_unsupported_error,
)


def _make_settings(api_key: str = "sk-test-1234abcd") -> AIProviderSettings:
    s = AIProviderSettings()
    s.api_key = api_key
    return s


def _make_mock_response(content: str = "hello", reasoning: str = "thinking...") -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.reasoning_content = reasoning
    choice = MagicMock()
    choice.message = msg
    usage = MagicMock()
    usage.prompt_tokens = 100
    usage.completion_tokens = 50
    usage.total_tokens = 150
    usage.prompt_tokens_details = MagicMock()
    usage.prompt_tokens_details.cached_tokens = 20
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    resp.id = "req-abc123"
    resp.model = "deepseek-v4-pro"
    return resp


def test_chat_does_not_send_forbidden_params():
    """chat() must never pass temperature/top_p/presence_penalty/frequency_penalty."""
    settings = _make_settings()
    client = DeepSeekClient(settings)

    mock_resp = _make_mock_response()
    mock_openai = MagicMock()
    mock_openai.return_value.chat.completions.create.return_value = mock_resp

    with patch("pa_agent.ai.deepseek_client._OpenAI", mock_openai):
        reply = client.chat([{"role": "user", "content": "hi"}])

    call_kwargs = mock_openai.return_value.chat.completions.create.call_args
    kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
    all_kwargs = {**(call_kwargs.args[0] if call_kwargs.args else {}), **kwargs}

    for forbidden in ("temperature", "top_p", "presence_penalty", "frequency_penalty"):
        assert forbidden not in all_kwargs, f"Forbidden param '{forbidden}' was sent to API"


def test_chat_extra_body_thinking_enabled():
    """DeepSeek v4 uses adaptive thinking plus reasoning_effort."""
    settings = _make_settings()
    settings.base_url = "https://api.deepseek.com"
    settings.model = "deepseek-v4-pro"
    settings.thinking = True
    settings.reasoning_effort = "max"
    client = DeepSeekClient(settings)

    mock_resp = _make_mock_response()
    mock_openai = MagicMock()
    mock_openai.return_value.chat.completions.create.return_value = mock_resp

    with patch("pa_agent.ai.deepseek_client._OpenAI", mock_openai):
        client.chat([{"role": "user", "content": "hi"}])

    call_kwargs = mock_openai.return_value.chat.completions.create.call_args
    kwargs = call_kwargs.kwargs
    assert kwargs["extra_body"]["thinking"]["type"] == "adaptive"
    assert kwargs["reasoning_effort"] == "max"


def test_completion_max_tokens_deepseek_cap():
    settings = _make_settings()
    settings.base_url = "https://api.deepseek.com"
    settings.model = "deepseek-v4-pro"
    assert _completion_max_tokens(settings, extra_body={}, effort="max") == 393_216


def test_completion_max_tokens_packy_claude_cap():
    settings = _make_settings()
    settings.base_url = "https://www.packyapi.com/v1"
    settings.model = "claude-sonnet-4-6"
    extra_body = {"thinking": {"type": "enabled", "budget_tokens": 127_999}}
    assert _completion_max_tokens(settings, extra_body=extra_body, effort="max") == 128_000


def test_packy_hoists_system_message_to_extra_body():
    from pa_agent.ai.deepseek_client import _prepare_chat_messages

    settings = _make_settings()
    settings.base_url = "https://www.packyapi.com/v1"
    settings.model = "claude-sonnet-4-6"
    msgs = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USR"},
    ]
    api_msgs, system = _prepare_chat_messages(settings, msgs)
    assert system == "SYS"
    assert api_msgs == [{"role": "user", "content": "USR"}]


def test_packy_claude_thinking_uses_budget_not_reasoning_effort():
    settings = _make_settings()
    settings.base_url = "https://www.packyapi.com/v1"
    settings.model = "claude-sonnet-4-6"
    settings.thinking = True
    from pa_agent.ai.deepseek_client import _resolve_thinking_params

    extra, effort = _resolve_thinking_params(settings, thinking=True, reasoning_effort="max")
    assert effort is None
    assert extra["thinking"]["type"] == "enabled"
    assert extra["thinking"]["budget_tokens"] == 127_999


def test_chat_sends_max_tokens_when_thinking():
    settings = _make_settings()
    settings.base_url = "https://api.deepseek.com"
    settings.model = "deepseek-v4-pro"
    settings.thinking = True
    settings.reasoning_effort = "medium"
    client = DeepSeekClient(settings)

    mock_resp = _make_mock_response()
    mock_openai = MagicMock()
    mock_openai.return_value.chat.completions.create.return_value = mock_resp

    with patch("pa_agent.ai.deepseek_client._OpenAI", mock_openai):
        client.chat([{"role": "user", "content": "hi"}])

    kwargs = mock_openai.return_value.chat.completions.create.call_args.kwargs
    assert kwargs["max_tokens"] == 393_216


def test_chat_kkai_sends_thinking_object_not_reasoning_effort():
    """KKAI Claude: thinking budget in extra_body; reasoning_effort rejected upstream."""
    settings = _make_settings()
    settings.base_url = "https://api.kkone.vip/v1"
    settings.model = "claude-opus-4-5"
    settings.thinking = True
    settings.reasoning_effort = "high"
    client = DeepSeekClient(settings)

    mock_resp = _make_mock_response()
    mock_openai = MagicMock()
    mock_openai.return_value.chat.completions.create.return_value = mock_resp

    with patch("pa_agent.ai.deepseek_client._OpenAI", mock_openai):
        client.chat([{"role": "user", "content": "hi"}])

    kwargs = mock_openai.return_value.chat.completions.create.call_args.kwargs
    assert kwargs["extra_body"]["thinking"] == {"type": "enabled", "budget_tokens": 524_287}
    assert "reasoning_effort" not in kwargs


def test_chat_kkai_thinking_off_sends_no_thinking_params():
    settings = _make_settings()
    settings.base_url = "https://api.kkone.vip/v1"
    settings.model = "claude-opus-4-5"
    settings.thinking = False
    client = DeepSeekClient(settings)

    mock_resp = _make_mock_response()
    mock_openai = MagicMock()
    mock_openai.return_value.chat.completions.create.return_value = mock_resp

    with patch("pa_agent.ai.deepseek_client._OpenAI", mock_openai):
        client.chat([{"role": "user", "content": "hi"}])

    kwargs = mock_openai.return_value.chat.completions.create.call_args.kwargs
    assert "reasoning_effort" not in kwargs
    assert "extra_body" not in kwargs


def test_chat_yunwu_opus_47_sends_adaptive_thinking():
    settings = _make_settings()
    settings.base_url = "https://yunwu.ai/v1"
    settings.model = "claude-opus-4-7"
    settings.thinking = True
    settings.reasoning_effort = "high"
    client = DeepSeekClient(settings)

    mock_resp = _make_mock_response()
    mock_openai = MagicMock()
    mock_openai.return_value.chat.completions.create.return_value = mock_resp

    with patch("pa_agent.ai.deepseek_client._OpenAI", mock_openai):
        client.chat([{"role": "user", "content": "hi"}])

    kwargs = mock_openai.return_value.chat.completions.create.call_args.kwargs
    assert kwargs["extra_body"]["thinking"] == {"type": "adaptive"}
    assert kwargs["extra_body"]["output_config"] == {"effort": "high"}
    assert kwargs["reasoning_effort"] == "high"


def test_chat_yunwu_thinking_off_sends_nothing():
    settings = _make_settings()
    settings.base_url = "https://yunwu.ai/v1"
    settings.model = "claude-opus-4-7"
    settings.thinking = False
    client = DeepSeekClient(settings)

    mock_resp = _make_mock_response()
    mock_openai = MagicMock()
    mock_openai.return_value.chat.completions.create.return_value = mock_resp

    with patch("pa_agent.ai.deepseek_client._OpenAI", mock_openai):
        client.chat([{"role": "user", "content": "hi"}])

    kwargs = mock_openai.return_value.chat.completions.create.call_args.kwargs
    assert "extra_body" not in kwargs
    assert "reasoning_effort" not in kwargs


def test_stream_kkai_passes_thinking_extra_body():
    settings = _make_settings()
    settings.base_url = "https://api.kkone.vip/v1"
    settings.model = "claude-opus-4-5"
    settings.thinking = True
    settings.reasoning_effort = "medium"
    client = DeepSeekClient(settings)

    chunk_reason = MagicMock()
    chunk_reason.choices = [MagicMock()]
    delta = MagicMock()
    delta.reasoning_content = "think"
    delta.content = None
    chunk_reason.choices[0].delta = delta
    chunk_reason.usage = None
    chunk_reason.id = "id-1"
    chunk_reason.model = "claude-opus-4-5"

    chunk_done = MagicMock()
    chunk_done.choices = []
    chunk_done.usage = MagicMock(
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        prompt_tokens_details=MagicMock(cached_tokens=0),
    )

    mock_openai = MagicMock()
    mock_openai.return_value.chat.completions.create.return_value = iter(
        [chunk_reason, chunk_done]
    )

    with patch("pa_agent.ai.deepseek_client._OpenAI", mock_openai):
        reply = client.stream_chat(
            [{"role": "user", "content": "hi"}],
            on_reasoning_token=lambda c: None,
        )

    kwargs = mock_openai.return_value.chat.completions.create.call_args.kwargs
    assert kwargs["extra_body"]["thinking"]["budget_tokens"] == 524_287
    assert "reasoning_effort" not in kwargs
    assert reply.reasoning_content == "think"


def test_chat_cancel_token_raises():
    """If cancel_token is set, chat() raises CancelledError before calling API."""
    from pa_agent.util.threading import CancelToken
    settings = _make_settings()
    client = DeepSeekClient(settings)

    token = CancelToken()
    token.set()

    mock_openai = MagicMock()
    with patch("pa_agent.ai.deepseek_client._OpenAI", mock_openai):
        with pytest.raises(CancelledError):
            client.chat([{"role": "user", "content": "hi"}], cancel_token=token)

    # API must NOT have been called
    mock_openai.return_value.chat.completions.create.assert_not_called()


def test_chat_no_plaintext_key_in_logs(caplog):
    """API key must not appear in log output."""
    import logging
    settings = _make_settings(api_key="sk-super-secret-9999")
    client = DeepSeekClient(settings)

    mock_resp = _make_mock_response()
    mock_openai = MagicMock()
    mock_openai.return_value.chat.completions.create.return_value = mock_resp

    with caplog.at_level(logging.DEBUG, logger="pa_agent.ai.deepseek_client"):
        with patch("pa_agent.ai.deepseek_client._OpenAI", mock_openai):
            client.chat([{"role": "user", "content": "hi"}])

    for record in caplog.records:
        assert "sk-super-secret-9999" not in record.getMessage(), (
            f"Plaintext API key found in log: {record.getMessage()}"
        )


def test_chat_returns_aireply_fields():
    """chat() returns an AIReply with all expected fields populated."""
    settings = _make_settings()
    client = DeepSeekClient(settings)

    mock_resp = _make_mock_response(content="answer", reasoning="thought")
    mock_openai = MagicMock()
    mock_openai.return_value.chat.completions.create.return_value = mock_resp

    with patch("pa_agent.ai.deepseek_client._OpenAI", mock_openai):
        reply = client.chat([{"role": "user", "content": "hi"}])

    assert isinstance(reply, AIReply)
    assert reply.content == "answer"
    assert reply.reasoning_content == "thought"
    assert reply.usage.prompt_tokens == 100
    assert reply.usage.completion_tokens == 50
    assert reply.request_id == "req-abc123"
    assert reply.latency_ms >= 0


def test_openclaw_is_not_treated_as_deepseek_model() -> None:
    assert _is_deepseek_model("openclaw") is False
    assert _is_deepseek_model("deepseek-v4-pro") is True


def test_openclaw_agent_request_includes_tool_choice_none() -> None:
    settings = _make_settings()
    settings.model = "openclaw"
    settings.base_url = "http://127.0.0.1:58579/v1"
    with patch("pa_agent.ai.qclaw_connector.detect_qclaw", return_value=True):
        assert _openclaw_agent_request_extra(settings) == {"tool_choice": "none"}


def test_stream_chat_passes_tool_choice_none_for_openclaw() -> None:
    settings = _make_settings()
    settings.model = "openclaw"
    settings.base_url = "http://127.0.0.1:58579/v1"
    settings.thinking = False
    client = DeepSeekClient(settings)

    mock_openai = MagicMock()
    mock_stream = iter([])

    def _create(**kwargs):
        mock_openai.last_kwargs = kwargs
        return mock_stream

    mock_openai.return_value.chat.completions.create.side_effect = _create

    with patch("pa_agent.ai.qclaw_connector.detect_qclaw", return_value=True):
        with patch("pa_agent.ai.deepseek_client._OpenAI", mock_openai):
            try:
                client.stream_chat([{"role": "user", "content": "hi"}])
            except Exception:
                pass

    extra = mock_openai.last_kwargs.get("extra_body") or {}
    assert extra.get("tool_choice") == "none"


def test_stream_options_retry_requires_explicit_unsupported_error() -> None:
    settings = _make_settings()
    client = DeepSeekClient(settings)
    mock_openai = MagicMock()
    calls: list[dict] = []

    def create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise TypeError("got an unexpected keyword argument 'stream_options'")
        return iter([])

    mock_openai.return_value.chat.completions.create.side_effect = create
    with patch("pa_agent.ai.deepseek_client._OpenAI", mock_openai):
        client.stream_chat([{"role": "user", "content": "hi"}])

    assert len(calls) == 2
    assert "stream_options" not in calls[1]
    assert _is_stream_options_unsupported_error(
        TypeError("got an unexpected keyword argument 'stream_options'")
    )


def test_stream_options_does_not_retry_uncertain_api_error() -> None:
    settings = _make_settings()
    client = DeepSeekClient(settings)
    mock_openai = MagicMock()
    mock_openai.return_value.chat.completions.create.side_effect = RuntimeError(
        "temporary upstream failure"
    )

    with patch("pa_agent.ai.deepseek_client._OpenAI", mock_openai):
        with pytest.raises(RuntimeError, match="temporary upstream failure"):
            client.stream_chat([{"role": "user", "content": "hi"}])

    mock_openai.return_value.chat.completions.create.assert_called_once()
    assert not _is_stream_options_unsupported_error(
        RuntimeError("temporary upstream failure")
    )


def test_mimo_chat_sends_enable_thinking_extra_body() -> None:
    settings = _make_settings()
    settings.base_url = "https://api.xiaomimimo.com/v1"
    settings.model = "mimo-v2-flash"
    settings.thinking = True
    client = DeepSeekClient(settings)

    mock_resp = _make_mock_response()
    mock_openai = MagicMock()
    mock_openai.return_value.chat.completions.create.return_value = mock_resp

    with patch("pa_agent.ai.deepseek_client._OpenAI", mock_openai):
        client.chat([{"role": "user", "content": "hi"}])

    kwargs = mock_openai.return_value.chat.completions.create.call_args.kwargs
    assert kwargs["extra_body"]["chat_template_kwargs"] == {"enable_thinking": True}
    assert kwargs["max_tokens"] == 65_536


def test_mimo_chat_patches_tool_call_messages_before_send() -> None:
    settings = _make_settings()
    settings.base_url = "https://api.xiaomimimo.com/v1"
    settings.model = "mimo-v2.5-pro"
    settings.thinking = False
    client = DeepSeekClient(settings)

    mock_resp = _make_mock_response()
    mock_openai = MagicMock()
    mock_openai.return_value.chat.completions.create.return_value = mock_resp

    messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "x", "arguments": "{}"},
                }
            ],
        },
    ]

    with patch("pa_agent.ai.deepseek_client._OpenAI", mock_openai):
        client.chat(messages)

    sent_messages = mock_openai.return_value.chat.completions.create.call_args.kwargs["messages"]
    assert sent_messages[1]["reasoning_content"] == ""

# ── 共享 OpenAI 客户端复用 / 关闭 ─────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_shared_clients():
    """每个用例前后清空共享客户端缓存，避免 mock 实例跨用例串用。"""
    from pa_agent.ai.deepseek_client import _reset_openai_client_cache

    _reset_openai_client_cache()
    yield
    _reset_openai_client_cache()


def _install_fake_openai(monkeypatch, response=None):
    """把 _OpenAI 换成本地工厂，记录创建与关闭情况（完全离线）。"""
    created: list = []

    class _FakeClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.closed = False
            self.chat = MagicMock()
            self.chat.completions.create.return_value = response or _make_mock_response()

        def close(self) -> None:
            self.closed = True

    def _factory(**kwargs):
        fake = _FakeClient(**kwargs)
        created.append(fake)
        return fake

    monkeypatch.setattr("pa_agent.ai.deepseek_client._OpenAI", _factory)
    return created


def test_chat_and_stream_reuse_one_openai_client(monkeypatch):
    """同一 (base_url, api_key, timeout) 的多次调用只创建一个 SDK 客户端。"""
    created = _install_fake_openai(monkeypatch)
    client = DeepSeekClient(_make_settings())

    client.chat([{"role": "user", "content": "hi"}])
    client.chat([{"role": "user", "content": "hi again"}])

    assert len(created) == 1
    assert created[0].kwargs["timeout"] == 600.0


def test_client_cache_key_separates_api_key_and_timeout(monkeypatch):
    """切换 key 或 timeout 会使用各自的客户端，不会串用连接池。"""
    created = _install_fake_openai(monkeypatch)
    client = DeepSeekClient(_make_settings(api_key="sk-key-a"))

    client.chat([{"role": "user", "content": "hi"}])
    client.chat([{"role": "user", "content": "hi"}], timeout_s=30.0)
    client._settings = _make_settings(api_key="sk-key-b")
    client.chat([{"role": "user", "content": "hi"}])

    assert len(created) == 3


def test_update_provider_closes_previous_client(monkeypatch):
    """update_provider 切换 provider 后旧客户端必须 close()。"""
    created = _install_fake_openai(monkeypatch)
    client = DeepSeekClient(_make_settings(api_key="sk-old"))

    client.chat([{"role": "user", "content": "hi"}])
    client.update_provider(_make_settings(api_key="sk-new"))
    client.chat([{"role": "user", "content": "hi"}])

    assert len(created) == 2
    assert created[0].closed is True, "旧 SDK 客户端未关闭，连接池会泄漏"
    assert created[1].closed is False


def test_release_closes_client_when_no_other_owner(monkeypatch):
    """release() 在没有其它持有者时立即关闭客户端。"""
    created = _install_fake_openai(monkeypatch)
    client = DeepSeekClient(_make_settings())

    client.chat([{"role": "user", "content": "hi"}])
    client.release()

    assert created[0].closed is True
    # 释放后仍可继续使用：会重新获取客户端。
    client.chat([{"role": "user", "content": "hi"}])
    assert len(created) == 2


def test_shared_client_keeps_alive_while_another_owner_uses_it(monkeypatch):
    """两个 DeepSeekClient 共用同一客户端时，先释放的一方不能把它关掉。"""
    created = _install_fake_openai(monkeypatch)
    first = DeepSeekClient(_make_settings())
    second = DeepSeekClient(_make_settings())

    first.chat([{"role": "user", "content": "hi"}])
    second.chat([{"role": "user", "content": "hi"}])
    assert len(created) == 1

    first.release()
    assert created[0].closed is False

    second.release()
    assert created[0].closed is True


def test_in_flight_request_defers_client_close(monkeypatch):
    """有在途请求时，退役的客户端延迟到请求结束再关闭（并发安全）。"""
    created = _install_fake_openai(monkeypatch)
    client = DeepSeekClient(_make_settings())

    client.chat([{"role": "user", "content": "hi"}])
    lease = client._acquire_client(600.0)

    client.release()
    assert created[0].closed is False, "在途请求期间不应关闭客户端"

    lease.release()
    assert created[0].closed is True
