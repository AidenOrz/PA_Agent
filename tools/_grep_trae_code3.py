"""读取 TRAE .mjs 文件中 77990 模块(d 函数)的代码。

用法:
    python tools/_grep_trae_code3.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    path = Path(r"C:\Users\Administrator\AppData\Local\Programs\TRAE SOLO CN\resources\app\node_modules\@byted-icube\solo-lite\dist\186.bbc5ebcf.mjs")
    content = path.read_text(encoding="utf-8", errors="replace")

    # 搜索 77990 模块定义
    print("=" * 60)
    print("搜索 '77990(e,t,r)' 模块定义")
    print("=" * 60)

    # 模块定义模式: 77990(e,t,r){...}
    patterns = [
        r"77990\(e,t,r\)\{",
        r"77990:\s*function",
        r",77990:\s*\(",
    ]
    for pat in patterns:
        for m in re.finditer(pat, content):
            start = m.start()
            # 输出模块定义前 5000 字符
            end = min(len(content), start + 5000)
            print(f"\n--- 模式 '{pat}' 命中 (位置 {start}) ---")
            print(content[start:end])
            print(f"--- 结束 ---\n")
            break  # 每个模式只输出第一个

    # 搜索 d 函数定义(可能在 77990 模块内)
    print("=" * 60)
    print("搜索 'function d(' 或 'd=function' 在 77990 附近")
    print("=" * 60)

    # 先找 77990 模块位置
    m77990 = re.search(r"77990\(e,t,r\)\{", content)
    if m77990:
        # 在 77990 模块范围内搜索 d 函数定义
        # 模块可能持续几千字符
        mod_start = m77990.start()
        mod_end = min(len(content), mod_start + 15000)
        mod_content = content[mod_start:mod_end]
        print(f"\n77990 模块内容 (前 15000 字符):")
        print(mod_content)
    else:
        print("未找到 77990 模块")

    return 0


if __name__ == "__main__":
    sys.exit(main())
