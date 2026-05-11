"""ORM 无关的通用工具函数."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

T = TypeVar("T")
V = TypeVar("V")


def filtered_in_sql_values(
    values: Iterable[V] | None,
    target_type_as: Callable[[V], T] = lambda x: x,
) -> list[T]:
    """过滤并去重 SQL IN 子句的值列表.

    跳过 ``None`` 和空字符串, 类型转换失败的值也会被忽略.
    """
    if not values:
        return []

    items: list[T] = []
    seen = set[T]()

    for item in values:
        if item is None or item == "":
            continue
        try:
            converted_value = target_type_as(item)
            if converted_value not in seen:
                seen.add(converted_value)
                items.append(converted_value)
        except (ValueError, TypeError):
            continue

    return items


def escape_like(value: str, escape_char: str = "\\") -> tuple[str, str]:
    """转义用于 SQL LIKE 的特殊字符并返回转义后的值和转义字符."""
    v = value.replace(escape_char, escape_char + escape_char)
    v = v.replace("%", escape_char + "%").replace("_", escape_char + "_")
    return v, escape_char
