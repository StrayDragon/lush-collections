#!/bin/env uv run

from __future__ import annotations

import ast
from collections.abc import Sequence
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SYNC_FILE = SCRIPT_DIR / "_sync" / "__init__.py"
ASYNC_FILE = SCRIPT_DIR / "_async" / "__init__.py"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    _ = path.write_text(content, encoding="utf-8")


def _find_class_def(module: ast.Module, class_name: str) -> ast.ClassDef | None:
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    return None


def _is_docstring_expr(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.Expr):
        return False
    value = stmt.value
    return isinstance(value, ast.Constant) and isinstance(value.value, str)


def _collect_method_docstrings_from_class(_src_text: str, class_def: ast.ClassDef) -> dict[str, str]:
    result: dict[str, str] = {}
    for node in class_def.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # 仅收集有 docstring 的方法
            if node.body and _is_docstring_expr(node.body[0]):
                content = ast.get_docstring(node, clean=True)
                if content is None:
                    continue
                result[node.name] = content
    return result


def _collect_methods_without_doc_from_class(class_def: ast.ClassDef) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    result: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in class_def.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            has_doc = bool(node.body and _is_docstring_expr(node.body[0]))
            if not has_doc:
                result[node.name] = node
    return result


def _compute_body_indent(lines: Sequence[str], def_lineno_1based: int) -> str:
    # 取函数定义行的缩进, 在其基础上+4空格作为函数体缩进
    def_line = lines[def_lineno_1based - 1]
    leading_spaces = len(def_line) - len(def_line.lstrip(" \t"))
    # 统一转换为使用空格缩进, 在现有基础上再加4
    return (" " * leading_spaces) + " " * 4


def _build_docstring_block(indent: str, content: str) -> str:
    # 使用多行风格, 三引号独占一行, 保持内容行原样, 结尾三引号独占一行
    inner_lines = content.splitlines()
    block_lines = [f'{indent}"""']
    block_lines.extend(f"{indent}{line}" for line in inner_lines)
    block_lines.append(f'{indent}"""')
    return "\n".join(block_lines) + "\n"


def _remove_stray_string_literals_in_class(async_text: str) -> str:
    # 文本扫描方式, 避免因当前文件不可解析而失败
    lines = async_text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    in_class = False
    class_indent = ""
    pending_class_doc_allowed = False
    in_func = False
    func_indent = ""
    at_func_start = False

    def is_triple_quote_line(s: str) -> bool:
        return '"""' in s

    def consume_triple_quoted_block(idx: int) -> int:
        # 返回块结束后一行的索引
        # 支持单行与多行三引号
        line = lines[idx]
        if line.count('"""') >= 2:
            return idx + 1
        j = idx + 1
        while j < len(lines):
            if '"""' in lines[j]:
                return j + 1
            j += 1
        return j

    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()

        # 进入/退出类
        if stripped.startswith("class AsyncWeComClient"):
            in_class = True
            class_indent = line[: len(line) - len(stripped)]
            pending_class_doc_allowed = True
            in_func = False
            out.append(line)
            i += 1
            continue

        if in_class and (
            line.startswith(class_indent)
            and stripped
            and not stripped.startswith(("def ", "async def ", "@"))
            and not line.startswith(class_indent + " ")
        ):
            # 遇到更小或相等缩进但不是装饰器/方法定义, 认为可能离开类(简单启发)
            in_class = False
            in_func = False

        # 方法开始/结束跟踪
        if in_class and stripped.startswith("async def "):
            in_func = True
            func_indent = line[: len(line) - len(stripped)] + " " * 4
            at_func_start = True
            out.append(line)
            i += 1
            continue

        if in_func:
            # 退出函数: 缩进小于函数体缩进
            current_indent = line[: len(line) - len(stripped)]
            if stripped and len(current_indent) < len(func_indent) and not line.startswith(func_indent):
                in_func = False
                at_func_start = False
                # 不消耗, 正常处理本行

        # 处理三引号块的保留/删除逻辑
        if in_class and is_triple_quote_line(line):
            allow = False
            if in_func and at_func_start:
                allow = True
            if not in_func and pending_class_doc_allowed:
                allow = True
            if allow:
                # 保留该docstring块
                end_idx = consume_triple_quoted_block(i)
                out.extend(lines[i:end_idx])
                i = end_idx
                if in_func and at_func_start:
                    at_func_start = False
                if not in_func and pending_class_doc_allowed:
                    pending_class_doc_allowed = False
                continue
            # 删除该三引号块
            i = consume_triple_quoted_block(i)
            continue

        # 其他普通行
        if in_func and at_func_start and stripped and not stripped.startswith("#"):
            # 已出现第一条非空非注释语句, 不再处于函数起始
            at_func_start = False
        out.append(line)
        i += 1

    return "".join(out)


def sync_docstrings() -> tuple[int, dict[str, str]]:
    """
    同步 `_sync/__init__.py` → `_async/__init__.py` 的方法 docstring.

    返回: (变更数量, 变更方法名到状态的映射)
    """
    if not SYNC_FILE.exists() or not ASYNC_FILE.exists():
        raise FileNotFoundError("同步所需文件不存在: _sync/__init__.py 或 _async/__init__.py")

    sync_text = _read_text(SYNC_FILE)
    async_text = _read_text(ASYNC_FILE)

    # 先清理之前可能错误插入的游离三引号字符串
    async_text = _remove_stray_string_literals_in_class(async_text)

    sync_mod = ast.parse(sync_text)
    async_mod = ast.parse(async_text)

    sync_cls = _find_class_def(sync_mod, "WeComClient")
    async_cls = _find_class_def(async_mod, "AsyncWeComClient")
    if sync_cls is None or async_cls is None:
        raise RuntimeError("未找到 WeComClient 或 AsyncWeComClient 类")

    sync_method_docs = _collect_method_docstrings_from_class(sync_text, sync_cls)
    async_methods_without_doc = _collect_methods_without_doc_from_class(async_cls)

    if not async_methods_without_doc:
        return 0, {}

    async_lines = async_text.splitlines(keepends=True)
    changed = 0
    changed_methods: dict[str, str] = {}

    # 先计算所有插入操作, 再统一按行号逆序插入, 避免位移
    pending_inserts: list[tuple[int, str]] = []
    for method_name, fn_def in async_methods_without_doc.items():
        content = sync_method_docs.get(method_name)
        if not content:
            continue

        # 优先使用函数体第一条语句的缩进与行号, 确保插入在函数体内部
        body_first_lineno = None
        body_first_indent = None
        if fn_def.body:
            first_stmt = fn_def.body[0]
            body_first_lineno = getattr(first_stmt, "lineno", fn_def.lineno + 1)
            line_text = async_lines[body_first_lineno - 1]
            body_first_indent = line_text[: len(line_text) - len(line_text.lstrip(" \t"))]

        indent = body_first_indent if body_first_indent is not None else _compute_body_indent(async_lines, fn_def.lineno)
        doc_block = _build_docstring_block(indent, content)

        insert_at = (body_first_lineno - 1) if body_first_lineno is not None else fn_def.lineno
        pending_inserts.append((insert_at, doc_block))
        changed_methods[method_name] = "inserted"
        changed += 1

    for insert_at, doc_block in sorted(pending_inserts, key=lambda x: x[0], reverse=True):
        async_lines[insert_at:insert_at] = [doc_block]

    if changed:
        _write_text(ASYNC_FILE, "".join(async_lines))

    return changed, changed_methods


def __main() -> None:
    changed, methods = sync_docstrings()
    if changed == 0:
        print("没有需要同步的 docstring, 异步文件已是最新状态.")
        return
    print(f"已同步 {changed} 个方法的 docstring:")
    for name in sorted(methods):
        print(f"  - {name}")


if __name__ == "__main__":
    __main()
