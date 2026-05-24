"""统一分页参数与结果模型.

提供 offset-based 和 cursor-based 两种分页模式的协议对象.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class OffsetPagination(BaseModel):
    """Offset-based 分页参数."""

    skip: int = Field(default=0, ge=0, description="跳过的记录数")
    limit: int = Field(default=20, ge=1, le=1000, description="返回的最大记录数")


class CursorPagination(BaseModel):
    """Cursor-based 分页参数.

    cursor 为上一页最后一条记录的标识 (通常是 ID 或时间戳),
    首次请求时为 None.
    """

    cursor: str | None = Field(default=None, description="游标标识, 首次请求为 None")
    limit: int = Field(default=20, ge=1, le=1000, description="返回的最大记录数")


class PageResult(BaseModel, Generic[T]):
    """Offset-based 分页结果."""

    items: list[T] = Field(default_factory=list, description="当前页的数据列表")
    total: int = Field(default=0, ge=0, description="符合条件的总记录数")
    skip: int = Field(default=0, ge=0, description="当前偏移量")
    limit: int = Field(default=20, ge=1, description="每页大小")

    @property
    def has_next(self) -> bool:
        """是否有下一页."""
        return self.skip + self.limit < self.total

    @property
    def page_count(self) -> int:
        """总页数."""
        if self.limit <= 0:  # pragma: no cover — Pydantic ge=1 已保证不可达
            return 0
        return (self.total + self.limit - 1) // self.limit


class CursorResult(BaseModel, Generic[T]):
    """Cursor-based 分页结果."""

    items: list[T] = Field(default_factory=list, description="当前页的数据列表")
    next_cursor: str | None = Field(default=None, description="下一页游标, 为 None 时表示无更多数据")

    @property
    def has_next(self) -> bool:
        """是否有下一页."""
        return self.next_cursor is not None
