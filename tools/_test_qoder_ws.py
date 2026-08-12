"""Test Qoder CN sidecar WebSocket JSON-RPC API.

The Qoder CN sidecar (cosy) exposes a WebSocket on port 36510. This script
probes various JSON-RPC method names to find the chat completions API.

Known model names (from logs):
  auto, qmodel_38max (Qwen3.8-Max), qmodel_latest (Qwen3.7-Max),
  qmodel (Qwen3.7-Plus), q36fmodel (Qwen3.6-Flash), dmodel (DeepSeek-V4-Pro),
  dfmodel (DeepSeek-V4-Flash), gm51model (GLM-5.2), kmodel (Kimi-K2.7-Code),
  mmodel (MiniMax-M2.7)
"""
from __future__ import annotations

import json
import sys
import time

# websocket-client may need: pip install websocket-client
try:
    import websocket  # type: ignore
except ImportError:
    print("ERROR: pip install websocket-client", file=sys.stderr)
    sys.exit(2)


WS_URL = "ws://127.0.0.1:36510"
MACHINE_TOKEN = "P1gATBmn3chlyQHqjAnVqs1k3SEM--aIm5D8vG1fl_nc5UVUsujXKzLQa3SvYYS0v7zjEIIOrsnWUtKw0ktH1c0c"
MACHINE_ID = "e9de1011-6113-443d-bebc-577da74ad439"
CLIENT_ID = "32633433-3830-452d-b964-38773a34332d"


def try_method(ws: websocket.WebSocket, method: str, params: dict, *, timeout: float = 3.0) -> tuple[bool, str]:
    """Send a JSON-RPC call and wait for response.

    Returns (success, response_text). Success = got a JSON response (not a
    network error), regardless of whether it's an error response.
    """
    req_id = method.replace("/", "_") + "_" + str(int(time.time() * 1000))[-6:]
    msg = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params,
    }
    payload = json.dumps(msg)
    print(f"\n→ send: {method}")
    print(f"  params: {json.dumps(params)[:200]}")
    try:
        ws.send(payload)
    except Exception as exc:
        return False, f"send error: {exc}"

    ws.settimeout(timeout)
    chunks: list[str] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = ws.recv()
        except websocket.WebSocketTimeoutException:
            break
        except Exception as exc:
            chunks.append(f"[recv error: {exc}]")
            break
        if not result:
            break
        chunks.append(result)
        # If we got a response, stop early (one message is enough for probe).
        if len(chunks) >= 5:
            break

    if not chunks:
        return False, "(no response, timeout)"
    text = "\n".join(chunks)
    return True, text[:800]


def main() -> int:
    print("=" * 60)
    print("Qoder CN WebSocket JSON-RPC probe")
    print(f"  URL: {WS_URL}")
    print("=" * 60)

    # Try connecting with various subprotocols / headers.
    print("\n[1] Connect (no auth)")
    try:
        ws = websocket.create_connection(WS_URL, timeout=5)
        print(f"  ✓ Connected")
    except Exception as exc:
        print(f"  ✗ Cannot connect: {exc}")
        return 1

    # Probe a list of likely JSON-RPC method names.
    probes: list[tuple[str, dict]] = [
        # ── ACP-style (Agent Client Protocol) ─────────────────────────────
        ("session/new", {"workspace": ""}),
        ("initialize", {"protocolVersion": 1}),
        ("agent/init", {}),
        # ── OpenAI-style chat completions ─────────────────────────────────
        ("chat.completions", {
            "model": "auto",
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False,
        }),
        ("chat/completions", {
            "model": "auto",
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False,
        }),
        # ── Qoder-style ───────────────────────────────────────────────────
        ("chat/send", {"message": "ping"}),
        ("chat/sendMessage", {"message": "ping"}),
        ("chat/sendMessage", {"content": "ping"}),
        ("chat/send", {"content": "ping", "model": "auto"}),
        ("chat/start", {"model": "auto"}),
        ("chat/create", {"model": "auto"}),
        ("chat/run", {"model": "auto", "messages": [{"role": "user", "content": "ping"}]}),
        ("model/list", {}),
        ("model/listModels", {}),
        ("models/list", {}),
        ("config/get", {}),
        ("config/list", {}),
        # ── Generic ───────────────────────────────────────────────────────
        ("ping", {}),
        ("version", {}),
        ("info", {}),
        ("help", {}),
        ("status", {}),
    ]

    print(f"\n[2] Probe {len(probes)} candidate methods (3s timeout each)")
    for method, params in probes:
        ok, text = try_method(ws, method, params, timeout=2.0)
        marker = "✓" if ok else "✗"
        first_line = text.split("\n", 1)[0][:200]
        print(f"  {marker} {method:30s} -> {first_line}")
        # Reconnect if socket is broken.
        try:
            ws.ping()
        except Exception:
            print("  (reconnecting)")
            try:
                ws.close()
            except Exception:
                pass
            try:
                ws = websocket.create_connection(WS_URL, timeout=5)
            except Exception as exc:
                print(f"  ✗ reconnect failed: {exc}")
                return 1

    ws.close()
    print("\n✓ Probe complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
