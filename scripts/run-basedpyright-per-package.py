#!/usr/bin/env python3
"""Run basedpyright per-package for staged files.

在受影响的包目录中运行 basedpyright, 确保使用正确的 pyproject.toml 配置.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def find_packages_from_args(args: list[str]) -> set[Path]:
    """从文件路径参数中提取受影响的包目录."""
    packages: set[Path] = set()
    for arg in args:
        try:
            rel = Path(arg).relative_to(ROOT)
        except ValueError:
            continue
        if rel.parts and rel.parts[0].startswith("lush-"):
            packages.add(ROOT / rel.parts[0])
    return packages


def run_basedpyright(pkg: Path) -> int:
    """在指定包目录中运行 basedpyright."""
    src = pkg / "src"
    if not src.is_dir():
        return 0

    print(f"== basedpyright {pkg.name}")
    result = subprocess.run(
        ["uv", "run", "--with", "basedpyright", "basedpyright", "src"],
        cwd=pkg,
    )
    return result.returncode


def main() -> None:
    files = sys.argv[1:] if len(sys.argv) > 1 else []
    if files:
        packages = find_packages_from_args(files)
    else:
        packages = {p for p in ROOT.glob("lush-*") if (p / "pyproject.toml").exists()}

    if not packages:
        return

    failed = False
    for pkg in sorted(packages):
        if run_basedpyright(pkg) != 0:
            failed = True

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
