#!/usr/bin/env python3
"""检查 library 源码 docstring 是否符合中文约定.

AGENTS.md 规定: 所有 library 源码 (非测试) 的 module/class/function docstring 使用中文.
若 docstring 存在但不含中文字符, 则视为违规.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _has_chinese(text: str) -> bool:
    return any("一" <= c <= "鿿" for c in text)


def _check_node(
    node: ast.AST,
    filepath: Path,
    name: str,
    kind: str,
    violations: list[str],
) -> None:
    docstring = ast.get_docstring(node)
    if docstring and not _has_chinese(docstring):
        lineno = getattr(node, "lineno", 0)
        violations.append(
            f"{filepath}:{lineno}: {kind} '{name}' docstring missing Chinese characters"
        )


def check_file(filepath: Path) -> list[str]:
    """检查单个文件的 docstring 约定."""
    source = filepath.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []

    violations: list[str] = []

    _check_node(tree, filepath, "<module>", "module", violations)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            _check_node(node, filepath, node.name, "class", violations)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _check_node(node, filepath, node.name, "function", violations)

    return violations


def main() -> None:
    violations: list[str] = []

    for pyproject in sorted(ROOT.glob("lush-*/pyproject.toml")):
        src_dir = pyproject.parent / "src"
        if not src_dir.is_dir():
            continue
        for pyfile in sorted(src_dir.rglob("*.py")):
            violations.extend(check_file(pyfile))

    if violations:
        for v in violations:
            print(v, file=sys.stderr)
        print(f"\n{len(violations)} docstring violation(s) found.", file=sys.stderr)
        sys.exit(1)

    print("All docstrings comply with Chinese language requirement.")


if __name__ == "__main__":
    main()
