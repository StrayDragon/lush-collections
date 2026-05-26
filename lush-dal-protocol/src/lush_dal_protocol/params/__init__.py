"""ORM 无关的操作参数对象."""

from .pagination import CursorPagination, CursorResult, OffsetPagination, PageResult

__all__ = [
    "CursorPagination",
    "CursorResult",
    "OffsetPagination",
    "PageResult",
]
