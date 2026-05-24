"""分页模型单元测试."""

from __future__ import annotations

from lush_dal_protocol.params.pagination import (
    CursorPagination,
    CursorResult,
    OffsetPagination,
    PageResult,
)


class TestOffsetPagination:
    def test_defaults(self) -> None:
        p = OffsetPagination()
        assert p.skip == 0
        assert p.limit == 20

    def test_custom_values(self) -> None:
        p = OffsetPagination(skip=10, limit=50)
        assert p.skip == 10
        assert p.limit == 50


class TestCursorPagination:
    def test_defaults(self) -> None:
        p = CursorPagination()
        assert p.cursor is None
        assert p.limit == 20

    def test_with_cursor(self) -> None:
        p = CursorPagination(cursor="abc123", limit=10)
        assert p.cursor == "abc123"


class TestPageResult:
    def test_has_next_true(self) -> None:
        r = PageResult[int](items=[1, 2, 3], total=10, skip=0, limit=3)
        assert r.has_next is True

    def test_has_next_false_on_last_page(self) -> None:
        r = PageResult[int](items=[9, 10], total=10, skip=8, limit=3)
        assert r.has_next is False

    def test_has_next_false_exact(self) -> None:
        r = PageResult[int](items=[1, 2, 3], total=3, skip=0, limit=3)
        assert r.has_next is False

    def test_page_count(self) -> None:
        r = PageResult[int](items=[], total=10, skip=0, limit=3)
        assert r.page_count == 4

    def test_page_count_exact_division(self) -> None:
        r = PageResult[int](items=[], total=9, skip=0, limit=3)
        assert r.page_count == 3

    def test_page_count_zero_total(self) -> None:
        r = PageResult[int](items=[], total=0, skip=0, limit=20)
        assert r.page_count == 0


class TestCursorResult:
    def test_has_next_true(self) -> None:
        r = CursorResult[str](items=["a", "b"], next_cursor="xyz")
        assert r.has_next is True

    def test_has_next_false(self) -> None:
        r = CursorResult[str](items=["a", "b"], next_cursor=None)
        assert r.has_next is False

    def test_empty_result(self) -> None:
        r = CursorResult[str](items=[], next_cursor=None)
        assert r.has_next is False
        assert r.items == []
