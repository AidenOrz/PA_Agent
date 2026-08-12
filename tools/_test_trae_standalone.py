"""TRAE Work CN 实际调用测试 - 自包含版本 (不依赖项目包)。

用法:
    python tools/_test_trae_standalone.py
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

# httpx 需要单独安装
try:
    import httpx
except ImportError:
    print("ERROR: httpx 未安装,请运行: pip install httpx")
    sys.exit(2)

# cryptography 用于 AES 解密
try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.padding import PKCS7
except ImportError:
    print("ERROR: cryptography 未安装,请运行: pip install cryptography")
    sys.exit(2)


# ─── 配置 ────────────────────────────────────────────────────────────────────

_APPDATA = os.environ.get("APPDATA", "").strip()
_TRAE_API_CHAT_PATH = "/api/agent/v3/llm_utils_chat"
_TRAE_APP_ID = "6eefa01c-1036-4c7e-9ca5-d891f63bfcd8"
_DEFAULT_TRAE_API_HOST = "https://trae-api-cn.mchost.guru"
_DEFAULT_INTERNAL_MODEL = "glm-5.2"

# JWT 正则
_JWT_RE = re.compile(
    rb"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}"
)

# ─── AES 解密 (与 trae_connector.py 相同) ────────────────────────────────────

_CRYPTO_SALT_A = bytes([
    82, 9, 106, 213, 48, 54, 165, 56, 191, 64, 163, 158, 129, 243, 215, 251,
    124, 227, 57, 130, 155, 47, 255, 135, 52, 142, 67, 68, 196, 222, 233, 203,
    84, 123, 148, 50, 166, 194, 35, 61, 238, 76, 149, 11, 66, 250, 195, 78, 8,
    46, 161, 102, 40, 217, 36, 178, 118, 91, 162, 73, 109, 139, 209, 37,
])
_CRYPTO_SALT_B = bytes([
    31, 221, 168, 51, 136, 7, 199, 49, 177, 18, 16, 89, 39, 128, 236, 95,
    96, 81, 127, 169, 25, 181, 74, 13, 45, 229, 122, 159, 147, 201, 156, 239,
    160, 224, 59, 77, 174, 42, 245, 176, 200, 235, 187, 60, 131, 83, 153, 97,
    23, 43, 4, 126, 186, 119, 214, 38, 225, 105, 20, 99, 85, 33, 12, 125,
])
_CRYPTO_SALT = bytes(a ^ b for a, b in zip(_CRYPTO_SALT_A, _CRYPTO_SALT_B))
_CRYPTO_HEADER = bytes([116, 99, 5, 16, 0, 0])
_CRYPTO_KEY_MATERIAL_LEN = 32


def decrypt_trae_value(encrypted: str) -> str | None:
    """解密 storage.json 中以 'tc\\x05' 前缀开头的值。"""
    try:
        raw = base64.b64decode(encrypted)
    except Exception:
        return None
    if len(raw) < 38 + 16:
        return None
    if raw[:6] != _CRYPTO_HEADER:
        return None
    key_material = raw[6:6 + _CRYPTO_KEY_MATERIAL_LEN]
    ciphertext = raw[6 + _CRYPTO_KEY_MATERIAL_LEN:]
    inner_hash = hashlib.sha512(key_material).digest()
    derived = hashlib.sha512(inner_hash + _CRYPTO_SALT).digest()
    aes_key = derived[0:16]
    iv = derived[16:32]
    try:
        decryptor = Cipher(algorithms.AES(aes_key), modes.CBC(iv)).decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = PKCS7(128).unpadder()
        plain = unpadder.update(padded) + unpadder.finalize()
    except Exception:
        return None
    if len(plain) < 64:
        return None
    stored_hash = plain[:64]
    body = plain[64:]
    if hashlib.sha512(body).digest() != stored_hash:
        return None
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return None


# ─── 路径解析 ────────────────────────────────────────────────────────────────

def find_data_dir() -> Path | None:
    candidates: list[Path] = []
    if _APPDATA:
        for name in ("TRAE SOLO CN", "Trae CN"):
            candidates.append(Path(_APPDATA) / name)
    candidates.append(Path.home() / ".trae-cn")
    for d in candidates:
        env = d / "ModularData" / "ckg_server" / "local_env.json"
        storage = d / "User" / "GlobalStorage" / "storage.json"
        storage_alt = d / "User" / "globalStorage" / "storage.json"
        if env.exists() or storage.exists() or storage_alt.exists():
            return d
    return None


def storage_path(data_dir: Path) -> Path | None:
    for rel in ("User/GlobalStorage/storage.json", "User/globalStorage/storage.json"):
        p = data_dir / rel
        if p.exists():
            return p
    return None


def env_path(data_dir: Path) -> Path | None:
    p = data_dir / "ModularData" / "ckg_server" / "local_env.json"
    return p if p.exists() else None


def logs_path(data_dir: Path) -> Path | None:
    p = data_dir / "logs"
    return p if p.exists() else None


# ─── Token 提取 ──────────────────────────────────────────────────────────────

def extract_token_from_storage(data_dir: Path) -> str | None:
    sp = storage_path(data_dir)
    if sp is None:
        return None
    try:
        storage = json.loads(sp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    auth_keys = [
        k for k in storage
        if k.startswith("iCubeAuthInfo://") and k != "iCubeAuthInfo://usertag"
    ]
    auth_keys.sort(key=lambda k: 0 if "icube.cloudide" in k else 1)
    for key in auth_keys:
        value = storage[key]
        if not isinstance(value, str) or len(value) < 50:
            continue
        plain = decrypt_trae_value(value)
        if plain is None:
            continue
        try:
            obj = json.loads(plain)
        except json.JSONDecodeError:
            continue
        token = obj.get("token", "")
        if token and isinstance(token, str) and token.startswith("eyJ"):
            return token
    return None


def jwt_issued_at(jwt: str) -> int | None:
    parts = jwt.split(".")
    if len(parts) != 3:
        return None
    try:
        pad = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(pad))
        return int(payload.get("iat", 0)) or None
    except Exception:
        return None


def is_jwt_expired(jwt: str) -> bool:
    parts = jwt.split(".")
    if len(parts) != 3:
        return True
    try:
        pad = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(pad))
        exp = int(payload.get("exp", 0))
        if exp <= 0:
            return True
        return exp <= time.time()
    except Exception:
        return True


def scan_logs_for_jwt(data_dir: Path) -> str | None:
    lp = logs_path(data_dir)
    if lp is None:
        return None
    best_token: str | None = None
    best_iat = 0
    for log_dir in sorted(lp.iterdir(), reverse=True):
        if not log_dir.is_dir():
            continue
        for log_file in log_dir.rglob("*.log"):
            try:
                data = log_file.read_bytes()
                if len(data) > 50 * 1024 * 1024:
                    continue
            except OSError:
                continue
            for m in _JWT_RE.finditer(data):
                jwt = m.group().decode("ascii", errors="replace")
                iat = jwt_issued_at(jwt)
                if iat is not None and iat > best_iat:
                    best_iat = iat
                    best_token = jwt
        if best_token:
            if not is_jwt_expired(best_token):
                return best_token
            break
    return best_token


def extract_token(data_dir: Path) -> str | None:
    # 1. 环境变量
    token = os.environ.get("TRAE_CN_API_TOKEN", "").strip()
    if token:
        return token
    # 2. 文件
    token_file = Path.home() / ".trae_cn_token"
    if token_file.exists():
        try:
            token = token_file.read_text(encoding="utf-8").strip()
            if token:
                return token
        except OSError:
            pass
    # 3. storage.json 解密
    token = extract_token_from_storage(data_dir)
    if token:
        return token
    # 4. 日志扫描
    token = scan_logs_for_jwt(data_dir)
    if token:
        return token
    return None


def read_device_info(data_dir: Path) -> dict[str, str]:
    info = {"device_id": "", "machine_id": ""}
    ep = env_path(data_dir)
    if ep is not None:
        try:
            env = json.loads(ep.read_text(encoding="utf-8"))
            info["device_id"] = str(env.get("device_id", ""))
        except (json.JSONDecodeError, OSError):
            pass
    sp = storage_path(data_dir)
    if sp is not None:
        try:
            storage = json.loads(sp.read_text(encoding="utf-8"))
            info["machine_id"] = str(storage.get("telemetry.machineId", ""))
        except (json.JSONDecodeError, OSError):
            pass
    return info


def get_api_host(data_dir: Path) -> str:
    ep = env_path(data_dir)
    if ep is not None:
        try:
            env = json.loads(ep.read_text(encoding="utf-8"))
            host_map = env.get("host_map", {})
            for _key, host in host_map.items():
                if host and host.startswith("https://"):
                    return host.rstrip("/")
        except (json.JSONDecodeError, OSError):
            pass
    return _DEFAULT_TRAE_API_HOST


def build_headers(token: str, device_id: str, machine_id: str) -> dict[str, str]:
    trace_id = uuid.uuid4().hex
    request_id = str(uuid.uuid4())
    return {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "x-app-id": _TRAE_APP_ID,
        "x-app-version": "default",
        "x-app-version-code": "20260630",
        "x-ide-version": "3.3.76",
        "x-ide-version-code": "20260630",
        "x-ide-version-type": "stable",
        "x-custom-trace-id": trace_id,
        "x-flow-traceparent": f"04-{trace_id}-{uuid.uuid4().hex[:16]}-01",
        "x-device-id": device_id,
        "x-machine-id": machine_id,
        "x-device-brand": "PA-Agent",
        "x-device-cpu": "Intel",
        "x-device-type": "windows",
        "x-os-version": "Windows",
        "request-traffic-type": "prod",
        "x-request-id": request_id,
        "x-trae-request-id": request_id,
        "Authorization": f"Bearer {token}",
    }


def parse_sse_event(raw_block: str) -> tuple[str, str]:
    event = ""
    data_parts: list[str] = []
    for line in raw_block.splitlines():
        if not line or line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_parts.append(line[len("data:"):].lstrip())
    return event, "\n".join(data_parts)


def extract_content_fields(data: object) -> tuple[str, str]:
    if data is None:
        return "", ""
    if isinstance(data, str):
        return data, ""
    if not isinstance(data, dict):
        return "", ""
    for wrapper in ("delta", "message", "plan_item", "data"):
        inner = data.get(wrapper)
        if isinstance(inner, dict):
            data = inner
            break
    content = data.get("content") or data.get("text") or ""
    reasoning = (
        data.get("reasoning_content")
        or data.get("reasoning")
        or data.get("thinking")
        or ""
    )
    if not isinstance(content, str):
        content = str(content) if content else ""
    if not isinstance(reasoning, str):
        reasoning = str(reasoning) if reasoning else ""
    return content, reasoning


# ─── 主流程 ──────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 60)
    print("TRAE Work CN 实际调用测试 (standalone)")
    print("=" * 60)

    print("\n[1] 定位 TRAE 数据目录 ...")
    data_dir = find_data_dir()
    if data_dir is None:
        print("  ✗ 未找到 TRAE Work CN 数据目录")
        return 1
    print(f"  ✓ data_dir = {data_dir}")

    print("\n[2] 提取 JWT Token ...")
    token = extract_token(data_dir)
    if not token:
        print("  ✗ 无法提取 Token")
        return 1
    print(f"  ✓ Token 长度 {len(token)}, 前 40 字符: {token[:40]}...")

    print("\n[3] 检查 Token 是否过期 ...")
    if is_jwt_expired(token):
        print("  ✗ Token 已过期")
        return 1
    print("  ✓ Token 未过期")

    print("\n[4] 读取 device 信息 ...")
    device_info = read_device_info(data_dir)
    device_id = device_info.get("device_id", "") or "unknown"
    machine_id = device_info.get("machine_id", "") or "unknown"
    print(f"  device_id = {device_id}")
    print(f"  machine_id = {machine_id}")

    print("\n[5] 构造请求 ...")
    api_host = get_api_host(data_dir)
    base_url = f"{api_host}{_TRAE_API_CHAT_PATH}"
    api_model = _DEFAULT_INTERNAL_MODEL
    print(f"  base_url = {base_url}")
    print(f"  api_model = {api_model}")

    headers = build_headers(token, device_id, machine_id)
    payload = {
        "user_input": "用中文回答: 1+1 等于几?",
        "model_name": api_model,
        "intent_name": "chat",
        "function": "utils",
        "chat_history": [],
    }

    print("\n[6] 发起 HTTP 调用 ...")
    t0 = time.monotonic()
    content_parts: list[str] = []
    reasoning_parts: list[str] = []

    try:
        with httpx.stream(
            "POST", base_url, headers=headers, json=payload, timeout=60.0
        ) as resp:
            print(f"  HTTP 状态码: {resp.status_code}")
            if resp.status_code != 200:
                body = resp.read().decode("utf-8", errors="replace")[:500]
                print(f"  响应体: {body}")
                return 1

            print("\n[7] 流式响应事件:")
            print("-" * 60)
            sse_buffer = ""
            event_count = 0
            for raw_line in resp.iter_lines():
                if raw_line is None:
                    continue
                if isinstance(raw_line, bytes):
                    raw_line = raw_line.decode("utf-8", errors="replace")
                if raw_line:
                    sse_buffer += raw_line + "\n"
                    continue
                if not sse_buffer.strip():
                    sse_buffer = ""
                    continue
                event, data_str = parse_sse_event(sse_buffer)
                sse_buffer = ""
                if not event:
                    continue
                event_count += 1
                data_preview = data_str[:200] if data_str else ""
                print(f"  [event #{event_count}] {event}: {data_preview}")
                data: object = data_str
                if data_str:
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        pass
                if event == "plan_item":
                    c_delta, r_delta = extract_content_fields(data)
                    if r_delta:
                        reasoning_parts.append(r_delta)
                    if c_delta:
                        content_parts.append(c_delta)
                elif event == "done":
                    print("  [done] 流式结束")
                    break
                elif event in ("error", "fatal_error"):
                    msg = (
                        data.get("message") or data.get("error") or data_str
                        if isinstance(data, dict)
                        else data_str
                    )
                    print(f"  ✗ 流式错误事件: {msg}")
                    return 1

    except httpx.HTTPError as exc:
        print(f"  ✗ 网络错误: {exc}")
        return 1

    elapsed_ms = (time.monotonic() - t0) * 1000
    print("-" * 60)
    print(f"\n[8] 结果汇总 (耗时 {elapsed_ms:.0f} ms):")
    print(f"  content 长度: {len(''.join(content_parts))} 字符")
    print(f"  reasoning 长度: {len(''.join(reasoning_parts))} 字符")

    full_content = "".join(content_parts)
    if full_content:
        print(f"\n[模型回复 content]:")
        print(full_content[:2000])
        print("\n✓ TRAE Work CN API 调用成功")
        return 0
    else:
        print("\n  ✗ 模型未返回任何 content")
        return 1


if __name__ == "__main__":
    sys.exit(main())
