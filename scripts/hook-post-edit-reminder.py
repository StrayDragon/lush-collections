#!/usr/bin/env python3
"""Claude Code PostToolUse hook: 检查编辑的文件是否需要同步更新 AGENTS.md.

当源码或依赖配置发生变更时, 提醒检查对应的 AGENTS.md 是否需要同步更新.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REMINDER_PATTERNS = ("src/", "pyproject.toml", "protocols/")
ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    file_path = payload.get("file_path", "")
    if not file_path:
        return

    if not any(p in file_path for p in REMINDER_PATTERNS):
        return

    # Walk up to find the nearest AGENTS.md
    rel = Path(file_path)
    try:
        rel = rel.relative_to(ROOT)
    except ValueError:
        pass

    for parent in list(rel.parents):
        candidate = ROOT / parent / "AGENTS.md"
        if candidate.exists():
            print(
                f"[doc-reminder] {file_path} changed — "
                f"if module structure/deps/coverage changed, update {parent}/AGENTS.md"
            )
            return

    if (ROOT / "AGENTS.md").exists():
        print(
            f"[doc-reminder] {file_path} changed — "
            "if module structure/deps/coverage changed, update AGENTS.md"
        )


if __name__ == "__main__":
    main()
