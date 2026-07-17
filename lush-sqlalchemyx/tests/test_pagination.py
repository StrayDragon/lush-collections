"""Pagination 工具单元测试."""

from __future__ import annotations

from typing import ClassVar

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Mapped, mapped_column

from lush_sqlalchemyx.base.dal import (
    BaseCU,
    BaseDTO,
    BasicAsyncBaseTable,
    CursorPagination,
    CursorResult,
    OffsetPagination,
    PageResult,
    build_cursor_stmt,
    build_offset_stmt,
    make_cursor_result,
    make_page_result,
)
from lush_sqlalchemyx.base.dal._pagination import decode_cursor, encode_cursor


class _PagTable(BasicAsyncBaseTable):
    __tablename__ = "pag_test_table"
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)


class _PagCU(BaseCU["_PagTable"]):
    _Table: ClassVar[type] = _PagTable
    name: str = ""


class _PagDTO(BaseDTO["_PagCU"]):
    _CU: ClassVar[type] = _PagCU
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str = ""


class TestCursorEncoding:
    def test_encode_decode_roundtrip_int(self) -> None:
        cursor = encode_cursor(42)
        assert decode_cursor(cursor) == "42"

    def test_encode_decode_roundtrip_str(self) -> None:
        cursor = encode_cursor("abc")
        assert decode_cursor(cursor) == "abc"


class TestBuildOffsetStmt:
    def test_default_pagination(self) -> None:
        stmt = build_offset_stmt(_PagTable, None)
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "LIMIT" in compiled
        assert "OFFSET" in compiled

    def test_custom_pagination(self) -> None:
        stmt = build_offset_stmt(_PagTable, OffsetPagination(skip=10, limit=5))
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "10" in compiled
        assert "5" in compiled

    def test_custom_order_by(self) -> None:
        stmt = build_offset_stmt(_PagTable, None, order_by=_PagTable.name.desc())
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "DESC" in compiled


class TestBuildCursorStmt:
    def test_no_cursor(self) -> None:
        stmt = build_cursor_stmt(_PagTable, None)
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert ">" not in compiled

    def test_with_cursor(self) -> None:
        cursor = encode_cursor(5)
        stmt = build_cursor_stmt(_PagTable, CursorPagination(cursor=cursor, limit=10))
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "5" in compiled
        assert ">" in compiled


class TestMakePageResult:
    def test_basic(self) -> None:
        result = make_page_result([_PagDTO(id=1, name="a")], 10, OffsetPagination(skip=0, limit=5))
        assert isinstance(result, PageResult)
        assert result.total == 10
        assert result.has_next is True

    def test_last_page(self) -> None:
        result = make_page_result([_PagDTO(id=1, name="a")], 1, OffsetPagination(skip=0, limit=5))
        assert result.has_next is False


class TestMakeCursorResult:
    def test_has_more(self) -> None:
        items = [_PagDTO(id=i, name=f"n{i}") for i in range(6)]
        result = make_cursor_result(items, 5)
        assert isinstance(result, CursorResult)
        assert result.has_next is True
        assert len(result.items) == 5
        assert result.next_cursor is not None

    def test_no_more(self) -> None:
        items = [_PagDTO(id=i, name=f"n{i}") for i in range(3)]
        result = make_cursor_result(items, 5)
        assert result.has_next is False
        assert result.next_cursor is None

    def test_empty(self) -> None:
        result = make_cursor_result([], 5)
        assert result.has_next is False

    def test_item_without_id_attr(self) -> None:
        """items 没有 id 属性时 cursor 为 None."""

        class _NoId(BaseModel):
            name: str = ""

        items = [_NoId(name=f"n{i}") for i in range(6)]
        result = make_cursor_result(items, 5)
        assert result.has_next is False
        assert result.next_cursor is None
