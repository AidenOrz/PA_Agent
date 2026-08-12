"""TRAE Work CN 实际调用测试 - 尝试多种认证方式。

用法:
    python tools/_test_trae_auth_variants.py
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

# 复用 standalone 的解密与读取逻辑
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _test_trae_standalone import (
    _CRYPTO_HEADER,
    _CRYPTO_KEY_MATERIAL_LEN,
    _CRYPTO_SALT,
    _DEFAULT_TRAE_API_HOST,
    _TRAE_API_CHAT_PATH,
    _TRAE_APP_ID,
    extract_token,
    find_data_dir,
    get_api_host,
    is_jwt_expired,
    jwt_issued_at,
    read_device_info,
)


def try_auth_variant(
    name: str,
    base_url: str,
    headers: dict[str, str],
    payload: dict,
    timeout: float = 30.0,
) -> tuple[int, str]:
    """Try one auth variant. Return (status, body_snippet)."""
    print(f"\n--- 尝试: {name} ---")
    print(f"  URL: {base_url}")
    print(f"  认证相关头:")
    for k, v in headers.items():
        if k.lower() in ("authorization", "x-ide-token", "x-cloudide-token",
                          "cloud-ide-jwt", "x-app-id", "cookie",
                          "x-cube-jwt", "x-cube-token"):
            preview = v if len(v) < 50 else v[:50] + "..."
            print(f"    {k}: {preview}")
    try:
        with httpx.stream("POST", base_url, headers=headers, json=payload, timeout=timeout) as resp:
            print(f"  HTTP {resp.status_code}")
            body = resp.read().decode("utf-8", errors="replace")[:500]
            print(f"  响应体: {body}")
            return resp.status_code, body
    except httpx.HTTPError as exc:
        print(f"  网络错误: {exc}")
        return -1, str(exc)


def main() -> int:
    print("=" * 60)
    print("TRAE Work CN 认证方式探索")
    print("=" * 60)

    data_dir = find_data_dir()
    if data_dir is None:
        print("✗ 未找到 TRAE Work CN 数据目录")
        return 1

    token = extract_token(data_dir)
    if not token:
        print("✗ 无法提取 Token")
        return 1
    print(f"\nToken 长度: {len(token)}")
    print(f"Token 前 40 字符: {token[:40]}")
    print(f"Token 是否过期: {is_jwt_expired(token)}")

    # 解析 JWT payload 看看里面有什么
    parts = token.split(".")
    if len(parts) == 3:
        pad = parts[1] + "=" * (-len(parts[1]) % 4)
        try:
            payload_data = json.loads(base64.urlsafe_b64decode(pad))
            print(f"\nJWT payload 字段: {list(payload_data.keys())}")
            # 不打印整个 payload,可能含敏感信息
            for k in ["iss", "aud", "exp", "iat", "sub", "user_id", "uid"]:
                if k in payload_data:
                    print(f"  {k}: {payload_data[k]}")
        except Exception:
            pass

    device_info = read_device_info(data_dir)
    device_id = device_info.get("device_id", "") or "unknown"
    machine_id = device_info.get("machine_id", "") or "unknown"

    api_host = get_api_host(data_dir)
    base_url_chat = f"{api_host}{_TRAE_API_CHAT_PATH}"
    base_url_super = f"{api_host}/api/ide/v1/super_completion_query"
    base_url_raw = f"{api_host}/api/ide/v1/llm_raw_chat"

    common_headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "x-app-id": _TRAE_APP_ID,
        "x-app-version": "default",
        "x-app-version-code": "20260630",
        "x-ide-version": "3.3.76",
        "x-ide-version-code": "20260630",
        "x-ide-version-type": "stable",
        "x-device-id": device_id,
        "x-machine-id": machine_id,
        "x-device-brand": "PA-Agent",
        "x-device-cpu": "Intel",
        "x-device-type": "windows",
        "x-os-version": "Windows",
        "request-traffic-type": "prod",
    }

    payload_chat = {
        "user_input": "1+1=?",
        "model_name": "glm-5.2",
        "intent_name": "chat",
        "function": "utils",
        "chat_history": [],
    }
    payload_super = {
        "query": "1+1=?",
        "model": "glm-5.2",
    }
    payload_raw = {
        "user_input": "1+1=?",
        "model_name": "glm-5.2",
    }

    # 测试各种认证头组合
    variants: list[tuple[str, str, dict, dict]] = [
        # llm_utils_chat + Authorization Bearer
        ("chat + Authorization Bearer", base_url_chat,
         {**common_headers, "Authorization": f"Bearer {token}"}, payload_chat),
        # llm_utils_chat + x-ide-token
        ("chat + x-ide-token", base_url_chat,
         {**common_headers, "x-ide-token": token}, payload_chat),
        # llm_utils_chat + Cloud-IDE-JWT
        ("chat + Cloud-IDE-JWT", base_url_chat,
         {**common_headers, "Cloud-IDE-JWT": token}, payload_chat),
        # super_completion_query + Authorization Bearer
        ("super + Authorization Bearer", base_url_super,
         {**common_headers, "Authorization": f"Bearer {token}"}, payload_super),
        # super_completion_query + x-ide-token
        ("super + x-ide-token", base_url_super,
         {**common_headers, "x-ide-token": token}, payload_super),
        # llm_raw_chat + x-ide-token
        ("raw + x-ide-token", base_url_raw,
         {**common_headers, "x-ide-token": token}, payload_raw),
        # llm_raw_chat + Authorization Bearer
        ("raw + Authorization Bearer", base_url_raw,
         {**common_headers, "Authorization": f"Bearer {token}"}, payload_raw),
    ]

    successes: list[str] = []
    for name, url, headers, payload in variants:
        status, body = try_auth_variant(name, url, headers, payload)
        if status == 200:
            successes.append(name)
            print(f"  ★★★ 成功! ★★★")

    print("\n" + "=" * 60)
    if successes:
        print(f"成功的认证方式: {successes}")
        return 0
    else:
        print("所有认证方式都失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
