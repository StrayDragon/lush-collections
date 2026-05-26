"""示例 2: 使用分页类型.

展示如何使用 lush-dal-protocol 的分页参数和返回值类型.
"""

from lush_dal_protocol.params.pagination import CursorPagination, CursorResult, OffsetPagination, PageResult

# 场景 1: Offset-based 分页


def create_offset_pagination(skip: int = 0, limit: int = 10) -> OffsetPagination:
    """创建 offset-based 分页参数."""
    return OffsetPagination(skip=skip, limit=limit)


def use_offset_pagination() -> PageResult[str]:
    """使用 offset-based 分页返回字符串列表."""
    items = ["item1", "item2", "item3"]
    total = 100
    pagination = OffsetPagination(skip=0, limit=10)

    return PageResult[str](
        items=items,
        total=total,
        skip=pagination.skip,
        limit=pagination.limit,
    )


def verify_offset_result(result: PageResult[str]) -> None:
    """验证 offset-based 分页结果."""
    assert result.total == 100
    assert len(result.items) == 3
    assert result.has_next is True  # 100 > 3 + 0
    assert result.page_count == 10  # (100 + 10 - 1) // 10
    assert result.skip == 0
    assert result.limit == 10


# 场景 2: Cursor-based 分页


def create_cursor_pagination(cursor: str | None = None, limit: int = 10) -> CursorPagination:
    """创建 cursor-based 分页参数."""
    return CursorPagination(cursor=cursor, limit=limit)


def use_cursor_pagination() -> CursorResult[str]:
    """使用 cursor-based 分页返回字符串列表."""
    items = ["item1", "item2", "item3"]
    next_cursor = "next_cursor_value"

    return CursorResult[str](
        items=items,
        next_cursor=next_cursor,
    )


def verify_cursor_result(result: CursorResult[str]) -> None:
    """验证 cursor-based 分页结果."""
    assert len(result.items) == 3
    assert result.next_cursor == "next_cursor_value"
    assert result.has_next is True


# 场景 3: 泛型推断


def process_generic_items() -> None:
    """验证泛型类型推断正确."""

    # 字符串结果
    str_result: PageResult[str] = use_offset_pagination()
    assert isinstance(str_result.items[0], str)

    # 整数结果
    int_result: CursorResult[int] = CursorResult[int](items=[1, 2, 3], next_cursor="xyz")
    assert int_result.items[0] == 1


# 场景 4: 默认参数


def use_default_pagination() -> None:
    """使用默认分页参数."""
    # OffsetPagination 默认值
    default_offset = OffsetPagination()
    assert default_offset.skip == 0
    assert default_offset.limit == 10

    # CursorPagination 默认值
    default_cursor = CursorPagination()
    assert default_cursor.cursor is None
    assert default_cursor.limit == 10
