"""Test Qoder CN sidecar via IPC Named Pipe — with non-blocking reads + timeout.

Uses a background thread to read from the pipe so the main thread can enforce
a hard timeout and avoid hanging forever.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

try:
    import win32file  # type: ignore
    import win32pipe  # type: ignore
    import pywintypes  # type: ignore
except ImportError:
    print("ERROR: pip install pywin32", file=sys.stderr)
    sys.exit(2)


INFO_JSON = Path(r"C:\Users\Administrator\AppData\Roaming\QoderCN\SharedClientCache\.info.json")


def get_pipe_path() -> str:
    info = json.loads(INFO_JSON.read_text(encoding="utf-8"))
    return info.get("ipcServerPath", "")


def connect_pipe(pipe_path: str):
    handle = win32file.CreateFile(
        pipe_path,
        win32file.GENERIC_READ | win32file.GENERIC_WRITE,
        0,
        None,
        win32file.OPEN_EXISTING,
        0,
        None,
    )
    return handle


def send_msg(handle, data: bytes) -> None:
    win32file.WriteFile(handle, data)


def recv_with_timeout(handle, timeout_s: float = 3.0) -> bytes:
    """Read from pipe using a background thread with hard timeout."""
    result: dict = {"data": b"", "error": None}

    def reader():
        chunks: list[bytes] = []
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                # ReadFile blocks until data arrives or pipe breaks.
                _, data = win32file.ReadFile(handle, 65536)
                if data:
                    chunks.append(data)
                    # After getting data, keep reading for a short window
                    # to collect the full message.
                    deadline = min(deadline, time.monotonic() + 0.8)
                else:
                    break
            except pywintypes.error as exc:
                if exc.winerror == 232:  # ERROR_NO_DATA
                    time.sleep(0.02)
                    continue
                if exc.winerror == 109:  # ERROR_BROKEN_PIPE
                    break
                result["error"] = f"winerror {exc.winerror}: {exc.strerror}"
                break
        result["data"] = b"".join(chunks)

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    t.join(timeout=timeout_s + 1.0)
    if t.is_alive():
        # Thread is still running (blocked on ReadFile). We can't kill it
        # cleanly, but as a daemon thread it won't block process exit.
        result["error"] = result["error"] or "timeout (reader still running)"
    return result["data"]


def try_rpc(handle, method: str, params: dict, *, timeout_s: float = 3.0) -> str:
    req_id = f"probe_{int(time.time() * 1000) % 100000}"
    msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
    payload = json.dumps(msg) + "\n"
    print(f"\n→ {method}")
    print(f"  params: {json.dumps(params)[:200]}")
    try:
        send_msg(handle, payload.encode("utf-8"))
    except Exception as exc:
        return f"send error: {exc}"
    data = recv_with_timeout(handle, timeout_s=timeout_s)
    if not data:
        return "(no response, timeout)"
    return data.decode("utf-8", errors="replace")[:800]


def main() -> int:
    print("=" * 60)
    print("Qoder CN IPC Named Pipe probe (non-blocking)")
    print("=" * 60)

    pipe_path = get_pipe_path()
    print(f"\nPipe path: {pipe_path}")
    if not pipe_path:
        print("✗ Cannot read pipe path")
        return 1

    print("\n[1] Connect to named pipe")
    try:
        handle = connect_pipe(pipe_path)
        print("  ✓ Connected")
    except Exception as exc:
        print(f"  ✗ Connect failed: {exc}")
        return 1

    try:
        win32pipe.SetNamedPipeHandleState(
            handle, win32pipe.PIPE_READMODE_MESSAGE, None, None
        )
        print("  ✓ PIPE_READMODE_MESSAGE")
    except Exception as exc:
        print(f"  ~ SetNamedPipeHandleState: {exc}")

    # Try just sending a bare newline first to see if the pipe is alive.
    print("\n[2] Bare connectivity test")
    try:
        send_msg(handle, b"\n")
        time.sleep(0.3)
        data = recv_with_timeout(handle, timeout_s=2.0)
        print(f"  recv: {data[:200] if data else b'(empty)'}")
    except Exception as exc:
        print(f"  ✗ {exc}")

    # Probe methods.
    probes: list[tuple[str, dict]] = [
        ("session/new", {"workspace": ""}),
        ("initialize", {"protocolVersion": 1}),
        ("initialize", {}),
        ("config/get", {}),
        ("model/list", {}),
        ("auth/status", {}),
        ("ping", {}),
        ("version", {}),
    ]

    print(f"\n[3] Probe {len(probes)} methods (3s timeout each)")
    for method, params in probes:
        result = try_rpc(handle, method, params, timeout_s=3.0)
        first_line = result.split("\n", 1)[0][:200]
        if "(no response" in result:
            marker = "✗"
        elif "error" in result.lower() and "✓" not in result:
            marker = "~"
        else:
            marker = "✓"
        print(f"  {marker} {method:20s} -> {first_line}")
        # Check pipe still alive.
        try:
            send_msg(handle, b"")
        except Exception:
            print("  (reconnecting)")
            try:
                win32file.CloseHandle(handle)
            except Exception:
                pass
            time.sleep(0.5)
            try:
                handle = connect_pipe(pipe_path)
                try:
                    win32pipe.SetNamedPipeHandleState(
                        handle, win32pipe.PIPE_READMODE_MESSAGE, None, None
                    )
                except Exception:
                    pass
            except Exception as exc:
                print(f"  ✗ reconnect failed: {exc}")
                return 1

    try:
        win32file.CloseHandle(handle)
    except Exception:
        pass
    print("\n✓ Done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
