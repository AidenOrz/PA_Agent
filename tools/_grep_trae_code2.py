"""读取 TRAE .mjs 文件中 send_message 和 Dh 函数的代码。

用法:
    python tools/_grep_trae_code2.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def find_around(content: str, keyword: str, window: int = 3000, max_hits: int = 3) -> None:
    print(f"\n{'=' * 60}\n搜索 '{keyword}'\n{'=' * 60}")
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
        print(f"--- 结束 ---")


def main() -> int:
    # 重点搜索 send_message 和 Dh 函数
    targets = [
        r"C:\Users\Administrator\AppData\Local\Programs\TRAE SOLO CN\resources\app\node_modules\@byted-icube\solo-lite\dist\186.bbc5ebcf.mjs",
        r"C:\Users\Administrator\AppData\Local\Programs\TRAE SOLO CN\resources\app\node_modules\@byted-icube\solo-lite\dist\244.1b906b8e.mjs",
    ]

    keywords = [
        "send_message",
        "i.Dh",
        "Dh(",
        "function Dh",
        "Dh=function",
        "Dh:e=>",
        "Dh(t)",
        "Dh(e",
    ]

    for path_str in targets:
        path = Path(path_str)
        if not path.exists():
            continue
        print(f"\n{'#' * 70}\n# 文件: {path.name}\n{'#' * 70}")
        content = path.read_text(encoding="utf-8", errors="replace")
        for kw in keywords:
            find_around(content, kw, window=2500, max_hits=2)

    return 0


if __name__ == "__main__":
    sys.exit(main())
