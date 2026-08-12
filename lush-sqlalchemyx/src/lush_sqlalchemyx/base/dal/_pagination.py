"""Cursor-based 和 offset-based 分页的 SQLAlchemy 实现.

提供通用的分页辅助函数, 可被 sync/async DAL 复用.

主键列名通过 ``pk_attr`` 配置 (默认 ``"id"``).
cursor 分页默认将 cursor 解码为 ``int``; 非 int 主键须自行提供 ``order_by``
并避免依赖默认 cursor 解码 (或自行编码/解码).
"""

from __future__ import annotations

import base64
from typing import Any, TypeVar

import sqlalchemy as sa
from lush_dal_protocol.params.pagination import (
    CursorPagination,
    CursorResult,
    OffsetPagination,
    PageResult,
)
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def encode_cursor(pk: int | str) -> str:
    """将主键编码为不透明的 cursor 字符串."""
    return base64.urlsafe_b64encode(str(pk).encode()).decode()


def decode_cursor(cursor: str) -> str:
    """将 cursor 解码为原始主键字符串."""
    return base64.urlsafe_b64decode(cursor.encode()).decode()


def build_offset_stmt(
    table: type[Any],
    pagination: OffsetPagination | None,
    *,
    order_by: Any | None = None,
    pk_attr: str = "id",
) -> sa.Select[Any]:
    """构造 offset-based 分页 SELECT 语句.

    未指定 ``order_by`` 时按 ``getattr(table, pk_attr)`` 排序.
    """
    p = pagination or OffsetPagination()
    stmt = sa.select(table)
    if order_by is not None:
        stmt = stmt.order_by(order_by)
    else:
        stmt = stmt.order_by(getattr(table, pk_attr))
    return stmt.offset(p.skip).limit(p.limit)


def build_cursor_stmt(
    table: type[Any],
    pagination: CursorPagination | None,
    *,
    pk_attr: str = "id",
) -> sa.Select[Any]:
    """构造 cursor-based 分页 SELECT 语句.

    使用 ``pk > cursor_value`` 的 keyset 分页方式.
    cursor 值默认按 ``int`` 解码; 非 int 主键请自备分页逻辑.
    """
    p = pagination or CursorPagination()
    id_col = getattr(table, pk_attr)
    stmt = sa.select(table).order_by(id_col)

    if p.cursor is not None:
        cursor_value = decode_cursor(p.cursor)
        stmt = stmt.where(id_col > int(cursor_value))

    return stmt.limit(p.limit + 1)


def make_page_result(items: list[T], total: int, pagination: OffsetPagination | None) -> PageResult[T]:
    """将查询结果组装为 PageResult."""
    p = pagination or OffsetPagination()
    return PageResult[T](items=items, total=total, skip=p.skip, limit=p.limit)


def make_cursor_result(items: list[T], limit: int, *, pk_attr: str = "id") -> CursorResult[T]:
    """将查询结果组装为 CursorResult.

    多取一条来判断是否有下一页; ``next_cursor`` 取自末条的 ``pk_attr``.
    """
    has_more = len(items) > limit
    if has_more:
        items = items[:limit]

    next_cursor: str | None = None
    if has_more and items:
        last_item = items[-1]
        pk = getattr(last_item, pk_attr, None)
        if pk is not None:
            next_cursor = encode_cursor(pk)

    return CursorResult[T](items=items, next_cursor=next_cursor)
