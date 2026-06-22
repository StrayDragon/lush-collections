"""Pagination 工具和 Repository 层集成测试."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from typing import Any, ClassVar

import pytest
import sqlalchemy as sa
from pydantic import ConfigDict
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.pool import NullPool

from lush_sqlalchemyx.base.dal import (
    AsyncSQLAlchemyRepository,
    BaseCU,
    BaseDTO,
    BasicAsyncBaseTable,
    CursorPagination,
    CursorResult,
    OffsetPagination,
    PageResult,
    SyncSQLAlchemyRepository,
    build_cursor_stmt,
    build_offset_stmt,
    make_cursor_result,
    make_page_result,
)
from lush_sqlalchemyx.base.dal._pagination import decode_cursor, encode_cursor

# ─── Models ──────────────────────────────────────────────────


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


# ─── Unit Tests for pagination utilities ──────────────────────


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
        from pydantic import BaseModel

        class _NoId(BaseModel):
            name: str = ""

        items = [_NoId(name=f"n{i}") for i in range(6)]
        result = make_cursor_result(items, 5)
        assert result.has_next is False
        assert result.next_cursor is None


# ─── Integration Tests: Sync Repository ──────────────────────


@pytest.fixture(scope="session")
def sync_engine(mysql_endpoint: Any) -> Generator[Any, None, None]:
    url = mysql_endpoint.sqlalchemy_url.replace("+aiomysql", "+pymysql")
    eng = create_engine(url, poolclass=NullPool, echo=False)
    _PagTable.metadata.create_all(eng)
    yield eng
    _PagTable.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture(scope="session")
def sync_repo_class(sync_engine: Any) -> type[SyncSQLAlchemyRepository[Any, Any, Any]]:
    class _TestRepo(SyncSQLAlchemyRepository["_PagTable", "_PagDTO", "_PagCU"]):
        _Table = _PagTable
        _DTO = _PagDTO
        _session_factory = staticmethod(lambda: Session(sync_engine))

    return _TestRepo


@pytest.fixture(autouse=True)
def _clean_table(sync_engine: Any) -> Generator[None, None, None]:
    with Session(sync_engine) as sess:
        sess.execute(sa.delete(_PagTable))
        sess.commit()
    yield
    with Session(sync_engine) as sess:
        sess.execute(sa.delete(_PagTable))
        sess.commit()


class TestSyncRepository:
    def test_create_and_get(self, sync_repo_class: Any) -> None:
        entity = sync_repo_class.create(_PagCU(name="hello"))
        assert entity.id > 0
        assert entity.name == "hello"

        fetched = sync_repo_class.get(entity.id)
        assert fetched is not None
        assert fetched.name == "hello"

    def test_get_dto(self, sync_repo_class: Any) -> None:
        entity = sync_repo_class.create(_PagCU(name="dto-test"))
        dto = sync_repo_class.get_dto(entity.id)
        assert dto is not None
        assert dto.id == entity.id
        assert dto.name == "dto-test"

    def test_get_nonexistent(self, sync_repo_class: Any) -> None:
        assert sync_repo_class.get(999999) is None
        assert sync_repo_class.get_dto(999999) is None

    def test_exists(self, sync_repo_class: Any) -> None:
        entity = sync_repo_class.create(_PagCU(name="exists"))
        assert sync_repo_class.exists(entity.id) is True
        assert sync_repo_class.exists(999999) is False

    def test_count(self, sync_repo_class: Any) -> None:
        assert sync_repo_class.count() == 0
        sync_repo_class.create(_PagCU(name="c1"))
        sync_repo_class.create(_PagCU(name="c2"))
        assert sync_repo_class.count() == 2

    def test_update(self, sync_repo_class: Any) -> None:
        entity = sync_repo_class.create(_PagCU(name="before"))
        updated = sync_repo_class.update(entity.id, _PagCU(name="after"))
        assert updated is not None
        assert updated.name == "after"

    def test_update_nonexistent(self, sync_repo_class: Any) -> None:
        assert sync_repo_class.update(999999, _PagCU(name="x")) is None

    def test_delete(self, sync_repo_class: Any) -> None:
        entity = sync_repo_class.create(_PagCU(name="del"))
        sync_repo_class.delete(entity.id)
        assert sync_repo_class.get(entity.id) is None

    def test_delete_nonexistent(self, sync_repo_class: Any) -> None:
        sync_repo_class.delete(999999)

    def test_bulk_create(self, sync_repo_class: Any) -> None:
        items = [_PagCU(name=f"bulk-{i}") for i in range(5)]
        entities = sync_repo_class.bulk_create(items)
        assert len(entities) == 5
        assert sync_repo_class.count() == 5

    def test_bulk_update(self, sync_repo_class: Any) -> None:
        entities = sync_repo_class.bulk_create([_PagCU(name=f"bu-{i}") for i in range(3)])
        pks = [e.id for e in entities]
        affected = sync_repo_class.bulk_update(pks, {"name": "changed"})
        assert affected == 3

    def test_bulk_update_empty(self, sync_repo_class: Any) -> None:
        assert sync_repo_class.bulk_update([], {"name": "x"}) == 0

    def test_bulk_delete(self, sync_repo_class: Any) -> None:
        entities = sync_repo_class.bulk_create([_PagCU(name=f"bd-{i}") for i in range(3)])
        pks = [e.id for e in entities]
        affected = sync_repo_class.bulk_delete(pks)
        assert affected == 3
        assert sync_repo_class.count() == 0

    def test_bulk_delete_empty(self, sync_repo_class: Any) -> None:
        assert sync_repo_class.bulk_delete([]) == 0

    def test_list_offset(self, sync_repo_class: Any) -> None:
        sync_repo_class.bulk_create([_PagCU(name=f"list-{i}") for i in range(10)])
        result = sync_repo_class.list(OffsetPagination(skip=0, limit=3))
        assert len(result.items) == 3
        assert result.total == 10
        assert result.has_next is True

        last_page = sync_repo_class.list(OffsetPagination(skip=9, limit=3))
        assert len(last_page.items) == 1
        assert last_page.has_next is False

    def test_create_rollback_on_error(self, sync_repo_class: Any, sync_engine: Any) -> None:
        """异常时 session 应 rollback 而非 commit."""
        import contextlib

        count_before = sync_repo_class.count()
        with contextlib.suppress(Exception):
            sync_repo_class.create(_PagCU(name="x" * 200))
        assert sync_repo_class.count() == count_before

    def test_list_cursor(self, sync_repo_class: Any) -> None:
        sync_repo_class.bulk_create([_PagCU(name=f"cur-{i}") for i in range(10)])

        page1 = sync_repo_class.list_cursor(CursorPagination(limit=3))
        assert len(page1.items) == 3
        assert page1.has_next is True

        page2 = sync_repo_class.list_cursor(CursorPagination(cursor=page1.next_cursor, limit=3))
        assert len(page2.items) == 3
        assert page2.has_next is True

        ids_p1 = {item.id for item in page1.items}
        ids_p2 = {item.id for item in page2.items}
        assert ids_p1.isdisjoint(ids_p2)


# ─── Integration Tests: Async Repository ─────────────────────


@pytest.fixture(scope="session")
def async_engine_sync_setup(mysql_endpoint: Any) -> Generator[Any, None, None]:
    """Session-scoped async engine setup (sync wrapper to avoid scope issues)."""
    import asyncio

    async def _create() -> Any:
        eng = create_async_engine(mysql_endpoint.sqlalchemy_url, poolclass=NullPool, echo=False)
        async with eng.begin() as conn:
            await conn.run_sync(_PagTable.metadata.create_all)
        return eng

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    eng = loop.run_until_complete(_create())
    yield eng

    async def _cleanup() -> None:
        async with eng.begin() as conn:
            await conn.run_sync(_PagTable.metadata.drop_all)
        await eng.dispose()

    loop.run_until_complete(_cleanup())


def _make_async_session_factory(engine: Any) -> Any:
    @asynccontextmanager
    async def factory() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(engine, expire_on_commit=False) as sess:
            yield sess

    return staticmethod(factory)


@pytest.fixture(scope="session")
def async_repo_class(async_engine_sync_setup: Any) -> type[AsyncSQLAlchemyRepository[Any, Any, Any]]:
    factory = _make_async_session_factory(async_engine_sync_setup)

    class _TestRepo(AsyncSQLAlchemyRepository["_PagTable", "_PagDTO", "_PagCU"]):
        _Table = _PagTable
        _DTO = _PagDTO
        _session_factory = factory

    return _TestRepo


class TestAsyncRepository:
    async def test_create_and_get(self, async_repo_class: Any) -> None:
        entity = await async_repo_class.create(_PagCU(name="async-hello"))
        assert entity.id > 0

        fetched = await async_repo_class.get(entity.id)
        assert fetched is not None
        assert fetched.name == "async-hello"

    async def test_get_dto(self, async_repo_class: Any) -> None:
        entity = await async_repo_class.create(_PagCU(name="async-dto"))
        dto = await async_repo_class.get_dto(entity.id)
        assert dto is not None
        assert dto.name == "async-dto"

    async def test_get_nonexistent(self, async_repo_class: Any) -> None:
        assert await async_repo_class.get(999999) is None
        assert await async_repo_class.get_dto(999999) is None

    async def test_exists(self, async_repo_class: Any) -> None:
        entity = await async_repo_class.create(_PagCU(name="async-exists"))
        assert await async_repo_class.exists(entity.id) is True
        assert await async_repo_class.exists(999999) is False

    async def test_count(self, async_repo_class: Any) -> None:
        assert await async_repo_class.count() == 0
        await async_repo_class.create(_PagCU(name="ac1"))
        await async_repo_class.create(_PagCU(name="ac2"))
        assert await async_repo_class.count() == 2

    async def test_update(self, async_repo_class: Any) -> None:
        entity = await async_repo_class.create(_PagCU(name="async-before"))
        updated = await async_repo_class.update(entity.id, _PagCU(name="async-after"))
        assert updated is not None
        assert updated.name == "async-after"

    async def test_update_nonexistent(self, async_repo_class: Any) -> None:
        assert await async_repo_class.update(999999, _PagCU(name="x")) is None

    async def test_delete(self, async_repo_class: Any) -> None:
        entity = await async_repo_class.create(_PagCU(name="async-del"))
        await async_repo_class.delete(entity.id)
        assert await async_repo_class.get(entity.id) is None

    async def test_delete_nonexistent(self, async_repo_class: Any) -> None:
        await async_repo_class.delete(999999)

    async def test_bulk_create(self, async_repo_class: Any) -> None:
        items = [_PagCU(name=f"async-bulk-{i}") for i in range(5)]
        entities = await async_repo_class.bulk_create(items)
        assert len(entities) == 5

    async def test_bulk_update(self, async_repo_class: Any) -> None:
        entities = await async_repo_class.bulk_create([_PagCU(name=f"abu-{i}") for i in range(3)])
        pks = [e.id for e in entities]
        affected = await async_repo_class.bulk_update(pks, {"name": "async-changed"})
        assert affected == 3

    async def test_bulk_update_empty(self, async_repo_class: Any) -> None:
        assert await async_repo_class.bulk_update([], {"name": "x"}) == 0

    async def test_bulk_delete(self, async_repo_class: Any) -> None:
        entities = await async_repo_class.bulk_create([_PagCU(name=f"abd-{i}") for i in range(3)])
        pks = [e.id for e in entities]
        affected = await async_repo_class.bulk_delete(pks)
        assert affected == 3

    async def test_bulk_delete_empty(self, async_repo_class: Any) -> None:
        assert await async_repo_class.bulk_delete([]) == 0

    async def test_list_offset(self, async_repo_class: Any) -> None:
        await async_repo_class.bulk_create([_PagCU(name=f"alist-{i}") for i in range(10)])
        result = await async_repo_class.list(OffsetPagination(skip=0, limit=3))
        assert len(result.items) == 3
        assert result.total == 10
        assert result.has_next is True

    async def test_list_cursor(self, async_repo_class: Any) -> None:
        await async_repo_class.bulk_create([_PagCU(name=f"acur-{i}") for i in range(10)])

        page1 = await async_repo_class.list_cursor(CursorPagination(limit=3))
        assert len(page1.items) == 3
        assert page1.has_next is True

        page2 = await async_repo_class.list_cursor(CursorPagination(cursor=page1.next_cursor, limit=3))
        assert len(page2.items) == 3
        assert page2.has_next is True

        ids_p1 = {item.id for item in page1.items}
        ids_p2 = {item.id for item in page2.items}
        assert ids_p1.isdisjoint(ids_p2)
