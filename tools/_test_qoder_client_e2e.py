"""End-to-end test for QoderClient via PA Agent's openclaw_qc route."""
import sys
import os

# Ensure pa_agent is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pa_agent.ai.qoder_connector import (
    detect_qoder_cn,
    is_qoder_cn_sidecar_running,
    qoder_cn_provider_settings,
    qoder_cn_health_check,
    resolve_qoder_cn_api_model,
)
from pa_agent.ai.qoder_client import QoderClient
from pa_agent.ai.client_factory import create_ai_client


def main():
    print("=" * 60)
    print("Qoder CN End-to-End Test")
    print("=" * 60)

    # Step 1: Detection
    print("\n--- Step 1: Detection ---")
    print(f"  detect_qoder_cn(): {detect_qoder_cn()}")
    print(f"  is_qoder_cn_sidecar_running(): {is_qoder_cn_sidecar_running()}")
    ok, msg = qoder_cn_health_check()
    print(f"  health_check: ok={ok}, msg={msg}")

    if not ok:
        print("\n*** Health check failed. Aborting. ***")
        sys.exit(1)

    # Step 2: Create settings
    print("\n--- Step 2: Provider Settings ---")
    settings = qoder_cn_provider_settings(model="openclaw_qc")
    if settings is None:
        print("  *** Failed to create provider settings ***")
        sys.exit(1)
    print(f"  model: {settings.model}")
    print(f"  base_url: {settings.base_url}")
    print(f"  api_key: {settings.api_key[:20]}...")
    print(f"  context_window: {settings.context_window}")
    print(f"  resolved api_model: {resolve_qoder_cn_api_model(settings.model)}")

    # Step 3: Create client via factory
    print("\n--- Step 3: Create AI Client (via factory) ---")
    client = create_ai_client(settings)
    print(f"  client type: {type(client).__name__}")
    assert isinstance(client, QoderClient), f"Expected QoderClient, got {type(client).__name__}"

    # Step 4: Stream chat with a simple question
    print("\n--- Step 4: stream_chat (model=auto) ---")
    messages = [
        {"role": "system", "content": "You are a helpful assistant. Reply concisely."},
        {"role": "user", "content": "Reply with exactly these words: hello world"},
    ]

    content_chunks: list[str] = []
    reasoning_chunks: list[str] = []

    reply = client.stream_chat(
        messages,
        on_content_token=lambda s: content_chunks.append(s),
        on_reasoning_token=lambda s: reasoning_chunks.append(s),
        timeout_s=120,
    )

    print(f"  content: {reply.content!r}")
    print(f"  reasoning_content: {reply.reasoning_content!r}")
    print(f"  usage: prompt={reply.usage.prompt_tokens} completion={reply.usage.completion_tokens} total={reply.usage.total_tokens}")
    print(f"  latency_ms: {reply.latency_ms:.0f}")
    print(f"  request_id: {reply.request_id}")
    print(f"  content_chunks received: {len(content_chunks)}")
    print(f"  reasoning_chunks received: {len(reasoning_chunks)}")

    assert "hello world" in reply.content.lower(), f"Expected 'hello world' in content, got: {reply.content!r}"
    print("\n  ✓ Content contains 'hello world'")

    # Step 5: Test with qmodel_38max
    print("\n--- Step 5: stream_chat (model=qmodel_38max) ---")
    settings2 = qoder_cn_provider_settings(model="openclaw_qc/qmodel_38max")
    if settings2 is None:
        print("  *** Failed to create provider settings for qmodel_38max ***")
        sys.exit(1)
    print(f"  model: {settings2.model}")
    print(f"  resolved api_model: {resolve_qoder_cn_api_model(settings2.model)}")

    client2 = create_ai_client(settings2)
    assert isinstance(client2, QoderClient), f"Expected QoderClient, got {type(client2).__name__}"

    reply2 = client2.stream_chat(
        [{"role": "user", "content": "Reply with exactly: pong"}],
        timeout_s=120,
    )
    print(f"  content: {reply2.content!r}")
    print(f"  reasoning_content: {reply2.reasoning_content!r}")
    print(f"  latency_ms: {reply2.latency_ms:.0f}")
    assert "pong" in reply2.content.lower(), f"Expected 'pong' in content, got: {reply2.content!r}"
    print("\n  ✓ Content contains 'pong'")

    # Step 6: Test multi-turn conversation (system + user)
    print("\n--- Step 6: stream_chat (multi-turn with system prompt) ---")
    messages3 = [
        {"role": "system", "content": "You are a calculator. Only output the numeric answer, nothing else."},
        {"role": "user", "content": "What is 2 + 3?"},
    ]
    reply3 = client.stream_chat(messages3, timeout_s=120)
    print(f"  content: {reply3.content!r}")
    print(f"  reasoning_content: {reply3.reasoning_content!r}")
    print(f"  latency_ms: {reply3.latency_ms:.0f}")
    assert "5" in reply3.content, f"Expected '5' in content, got: {reply3.content!r}"
    print("\n  ✓ Content contains '5'")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED ✓")
    print("=" * 60)


if __name__ == "__main__":
    main()
