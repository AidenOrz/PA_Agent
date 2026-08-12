"""读取 TRAE .mjs 文件中关键字周围的代码(用于研究 API 调用)。

用法:
    python tools/_grep_trae_code.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def find_around(content: str, keyword: str, window: int = 1500, max_hits: int = 5) -> None:
    """Find all occurrences of keyword and print window chars around each."""
    print(f"\n{'=' * 60}\n搜索 '{keyword}' (显示前后 {window} 字符)\n{'=' * 60}")
    hits = 0
    for m in re.finditer(re.escape(keyword), content):
        if hits >= max_hits:
            print(f"\n... (more hits omitted)")
            break
        hits += 1
        start = max(0, m.start() - window)
        end = min(len(content), m.end() + window)
        snippet = content[start:end]
        print(f"\n--- 命中 #{hits} (位置 {m.start()}) ---")
        print(snippet)
        print(f"--- 命中 #{hits} 结束 ---")


def main() -> int:
    targets = [
        r"C:\Users\Administrator\AppData\Local\Programs\TRAE SOLO CN\resources\app\node_modules\@byted-icube\solo-lite\dist\186.bbc5ebcf.mjs",
        r"C:\Users\Administrator\AppData\Local\Programs\TRAE SOLO CN\resources\app\node_modules\@byted-icube\solo-lite\dist\244.1b906b8e.mjs",
    ]
    keywords = [
        "super_completion_query",
        "llm_raw_chat",
    ]

    for path_str in targets:
        path = Path(path_str)
        if not path.exists():
            print(f"\n✗ 文件不存在: {path}")
            continue
        print(f"\n{'#' * 70}\n# 文件: {path.name} (大小 {path.stat().st_size} bytes)\n{'#' * 70}")
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            print(f"读取失败: {exc}")
            continue
        for kw in keywords:
            find_around(content, kw, window=2000, max_hits=3)

    return 0


if __name__ == "__main__":
    sys.exit(main())
