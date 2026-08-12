"""Extract model names from TRAE SOLO CN IndexedDB / ModularData / all data files.

Searches all binary files in TRAE's data directory for model_id patterns.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

DATA_DIRS = [
    Path(r"C:\Users\Administrator\AppData\Roaming\TRAE SOLO CN\IndexedDB"),
    Path(r"C:\Users\Administrator\AppData\Roaming\TRAE SOLO CN\ModularData"),
    Path(r"C:\Users\Administrator\AppData\Roaming\TRAE SOLO CN\User"),
]

# Pattern: <label>_<n>__<model_name>
MODEL_ID_RE = re.compile(rb"(solo_agent_lite|solo_work_lite|solo_coder|solo_agent_remote|solo_work_remote|solo_design_lite|solo_design_remote|agent)_(\d+)__([a-zA-Z0-9_.\-]+)")
# Broader: any "model_name":"..." or "model":"..."
MODEL_FIELD_RE = re.compile(rb'"model(?:_name|_id|Name|Id)?"\s*:\s*"([a-zA-Z0-9_.\-]+)"')
# Chat model field: chat_model=xxx
CHAT_MODEL_RE = re.compile(rb'chat_model=([a-zA-Z0-9_.\-]+)')


def scan_file(path: Path, model_ids: dict, model_names: set, chat_models: set) -> int:
    """Scan one file, return number of matches found."""
    try:
        data = path.read_bytes()
    except (OSError, PermissionError):
        return 0
    if not data:
        return 0

    count = 0
    for m in MODEL_ID_RE.finditer(data):
        label = m.group(1).decode()
        model_name = m.group(3).decode()
        if label not in model_ids:
            model_ids[label] = set()
        if model_name not in model_ids[label]:
            model_ids[label].add(model_name)
            count += 1
        model_names.add(model_name)

    for m in MODEL_FIELD_RE.finditer(data):
        name = m.group(1).decode()
        if name and not name.startswith("$") and len(name) < 80:
            model_names.add(name)
            count += 1

    for m in CHAT_MODEL_RE.finditer(data):
        name = m.group(1).decode()
        if name:
            chat_models.add(name)
            count += 1

    return count


def main() -> int:
    model_ids: dict[str, set[str]] = {}
    model_names: set[str] = set()
    chat_models: set[str] = set()

    for data_dir in DATA_DIRS:
        if not data_dir.exists():
            continue
        print(f"\n扫描: {data_dir}")
        file_count = 0
        for path in data_dir.rglob("*"):
            if not path.is_file():
                continue
            # Skip very large files (>20MB) and known locked files.
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > 20 * 1024 * 1024 or size == 0:
                continue
            file_count += 1
            scan_file(path, model_ids, model_names, chat_models)
        print(f"  扫描了 {file_count} 个文件")

    print("\n" + "=" * 60)
    print("模型 ID 列表 (按 label 分组)")
    print("=" * 60)
    for label in sorted(model_ids.keys()):
        models = sorted(model_ids[label])
        print(f"\n[{label}] ({len(models)} 个)")
        for i, m in enumerate(models, 1):
            print(f"  {i:2d}. {m}")

    print("\n" + "=" * 60)
    print(f"所有 model_name/model 字段值 ({len(model_names)} 个)")
    print("=" * 60)
    for i, m in enumerate(sorted(model_names), 1):
        print(f"  {i:2d}. {m}")

    print("\n" + "=" * 60)
    print(f"chat_model 字段值 ({len(chat_models)} 个)")
    print("=" * 60)
    for i, m in enumerate(sorted(chat_models), 1):
        print(f"  {i:2d}. {m}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
