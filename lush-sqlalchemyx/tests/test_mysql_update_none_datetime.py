"""复现 / 防护: 全字段 CU 显式 None + update_only_set_by_id + MySQL datetime.

迁移场景下 CU 经 Pydantic 校验后常带显式 ``None``; 默认 ``none_policy="ignore"``
避免写入 UPDATE. MySQL 5.7 非严格模式下 ``allow`` 可复现 zero-date;
MySQL 8 严格模式下 ``allow`` 应报错. sync / async API 对拍.
"""

from __future__ import annotations

import datetime
from collections.abc import AsyncGenerator, Generator
from typing import Any, ClassVar

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError, StatementError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import NullPool

from lush_sqlalchemyx.base.dal import (
    AsyncBaseDAL,
    AsyncSqlATableBase,
    BaseCU,
    BaseDTO,
    BasicAsyncBaseTable,
    BasicSyncBaseTable,
    SyncBaseDAL,
    SyncSqlATableBase,
    setup_dal_hooks,
)
from tests.conftest import (
    MYSQL_SQL_MODE_NONSTRICT,
    MYSQL_SQL_MODE_STRICT,
    _MySQLEndpoint,
)
from tests.oracle.update_none import AssignStyle, oracle_assign_attr, oracle_attr_is_dirty, oracle_flush_assign_none

setup_dal_hooks()

_TS = datetime.datetime(2026, 8, 4, 21, 32, 0)
_STRICT_WRITE_ERRORS = (IntegrityError, OperationalError, DBAPIError, StatementError)


# ── sync models ──────────────────────────────────────────────


class _BuggySyncTable(BasicSyncBaseTable):
    __tablename__ = "buggy_update_sync"

    id: Mapped[int] = mapped_column(sa.BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    create_datetime: Mapped[datetime.datetime] = mapped_column(sa.DateTime, nullable=False)
    update_datetime: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime,
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        server_onupdate=sa.text("CURRENT_TIMESTAMP"),
    )
    update_operator_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)


class _BuggySyncCU(BaseCU["_BuggySyncTable"]):
    _Table: ClassVar[type[_BuggySyncTable]] = _BuggySyncTable
    user_id: int
    create_datetime: datetime.datetime | None = None
    update_datetime: datetime.datetime | None = None
    update_operator_id: int | None = None


class _BuggySyncDTO(BaseDTO["_BuggySyncCU"]):
    _CU: ClassVar[type[_BuggySyncCU]] = _BuggySyncCU
    id: int
    user_id: int
    create_datetime: datetime.datetime | None = None
    update_datetime: datetime.datetime | None = None
    update_operator_id: int | None = None


class _BuggySyncDAL(SyncBaseDAL["_BuggySyncTable", _BuggySyncDTO, _BuggySyncCU]):
    _Table = _BuggySyncTable
    _DTO = _BuggySyncDTO


# ── async models (独立表名, 避免与 sync MetaData 冲突) ─────────


class _BuggyAsyncTable(BasicAsyncBaseTable):
    __tablename__ = "buggy_update_async"

    id: Mapped[int] = mapped_column(sa.BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    create_datetime: Mapped[datetime.datetime] = mapped_column(sa.DateTime, nullable=False)
    update_datetime: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime,
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        server_onupdate=sa.text("CURRENT_TIMESTAMP"),
    )
    update_operator_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)


class _BuggyAsyncCU(BaseCU["_BuggyAsyncTable"]):
    _Table: ClassVar[type[_BuggyAsyncTable]] = _BuggyAsyncTable
    user_id: int
    create_datetime: datetime.datetime | None = None
    update_datetime: datetime.datetime | None = None
    update_operator_id: int | None = None


class _BuggyAsyncDTO(BaseDTO["_BuggyAsyncCU"]):
    _CU: ClassVar[type[_BuggyAsyncCU]] = _BuggyAsyncCU
    id: int
    user_id: int
    create_datetime: datetime.datetime | None = None
    update_datetime: datetime.datetime | None = None
    update_operator_id: int | None = None


class _BuggyAsyncDAL(AsyncBaseDAL["_BuggyAsyncTable", _BuggyAsyncDTO, _BuggyAsyncCU]):
    _Table = _BuggyAsyncTable
    _DTO = _BuggyAsyncDTO


def _migration_cu_sync() -> _BuggySyncCU:
    return _BuggySyncCU(user_id=1, create_datetime=_TS, update_datetime=None, update_operator_id=2)


def _migration_cu_async() -> _BuggyAsyncCU:
    return _BuggyAsyncCU(user_id=1, create_datetime=_TS, update_datetime=None, update_operator_id=2)


def _set_sql_mode_sync(session: Session, sql_mode: str) -> None:
    session.execute(text("SET SESSION sql_mode = :mode"), {"mode": sql_mode})


async def _set_sql_mode_async(session: AsyncSession, sql_mode: str) -> None:
    await session.execute(text("SET SESSION sql_mode = :mode"), {"mode": sql_mode})


def _raw_update_dt_sync(session: Session, table: str, entity_id: int) -> Any:
    return session.execute(
        text(f"SELECT update_datetime FROM {table} WHERE id = :id"),  # noqa: S608
        {"id": entity_id},
    ).scalar_one()


async def _raw_update_dt_async(session: AsyncSession, table: str, entity_id: int) -> Any:
    return (
        await session.execute(
            text(f"SELECT update_datetime FROM {table} WHERE id = :id"),  # noqa: S608
            {"id": entity_id},
        )
    ).scalar_one()


def _cast_update_dt_sync(session: Session, table: str, entity_id: int) -> str:
    raw = session.execute(
        text(f"SELECT CAST(update_datetime AS CHAR) FROM {table} WHERE id = :id"),  # noqa: S608
        {"id": entity_id},
    ).scalar_one()
    return str(raw)


async def _cast_update_dt_async(session: AsyncSession, table: str, entity_id: int) -> str:
    raw = (
        await session.execute(
            text(f"SELECT CAST(update_datetime AS CHAR) FROM {table} WHERE id = :id"),  # noqa: S608
            {"id": entity_id},
        )
    ).scalar_one()
    return str(raw)


def _seed_sync(session: Session) -> int:
    entity = _BuggySyncTable(user_id=1, create_datetime=_TS, update_datetime=_TS, update_operator_id=2)
    session.add(entity)
    session.flush()
    return int(entity.id)


async def _seed_async(session: AsyncSession) -> int:
    entity = _BuggyAsyncTable(user_id=1, create_datetime=_TS, update_datetime=_TS, update_operator_id=2)
    session.add(entity)
    await session.flush()
    return int(entity.id)


def _sync_session_for(endpoint: _MySQLEndpoint) -> Generator[Session, None, None]:
    engine = create_engine(endpoint.sync_sqlalchemy_url, poolclass=NullPool)
    table = _BuggySyncTable.__table__
    SyncSqlATableBase.metadata.create_all(engine, tables=[table])
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
        session.rollback()
    finally:
        session.close()
        SyncSqlATableBase.metadata.drop_all(engine, tables=[table])
        engine.dispose()


async def _async_session_for(endpoint: _MySQLEndpoint) -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(endpoint.sqlalchemy_url, poolclass=NullPool)
    table = _BuggyAsyncTable.__table__

    async with engine.begin() as conn:
        await conn.run_sync(AsyncSqlATableBase.metadata.create_all, tables=[table])

    session = async_sessionmaker(engine, expire_on_commit=False)()
    try:
        yield session
        await session.rollback()
    finally:
        await session.close()
        async with engine.begin() as conn:
            await conn.run_sync(AsyncSqlATableBase.metadata.drop_all, tables=[table])
        await engine.dispose()


@pytest.fixture
def mysql_sync_session(mysql_endpoint: _MySQLEndpoint) -> Generator[Session, None, None]:
    yield from _sync_session_for(mysql_endpoint)


@pytest.fixture
def mysql57_sync_session(mysql57_endpoint: _MySQLEndpoint) -> Generator[Session, None, None]:
    yield from _sync_session_for(mysql57_endpoint)


@pytest.fixture
def mysql8_sync_session(mysql8_endpoint: _MySQLEndpoint) -> Generator[Session, None, None]:
    yield from _sync_session_for(mysql8_endpoint)


@pytest.fixture
async def mysql57_async_session(mysql57_endpoint: _MySQLEndpoint) -> AsyncGenerator[AsyncSession, None]:
    async for session in _async_session_for(mysql57_endpoint):
        yield session


@pytest.fixture
async def mysql8_async_session(mysql8_endpoint: _MySQLEndpoint) -> AsyncGenerator[AsyncSession, None]:
    async for session in _async_session_for(mysql8_endpoint):
        yield session


class TestOracleAssignNoneEquivalent:
    @pytest.mark.parametrize("style", ["setattr", "dot"])
    def test_assign_none_marks_dirty_same(self, mysql_sync_session: Session, style: AssignStyle) -> None:
        eid = _seed_sync(mysql_sync_session)
        entity = mysql_sync_session.get(_BuggySyncTable, eid)
        assert entity is not None
        assert not oracle_attr_is_dirty(entity, "update_datetime")
        oracle_assign_attr(entity, "update_datetime", None, style=style)
        assert oracle_attr_is_dirty(entity, "update_datetime")
        mysql_sync_session.rollback()


class TestUpdateOnlySetNonePolicy:
    def test_ignore_keeps_datetime(self, mysql_sync_session: Session) -> None:
        eid = _seed_sync(mysql_sync_session)
        before = _raw_update_dt_sync(mysql_sync_session, "buggy_update_sync", eid)
        assert _BuggySyncDAL.update_only_set_by_id(mysql_sync_session, eid, _migration_cu_sync(), none_policy="ignore") is not None
        mysql_sync_session.flush()
        assert _raw_update_dt_sync(mysql_sync_session, "buggy_update_sync", eid) == before

    def test_forbid_raises(self, mysql_sync_session: Session) -> None:
        eid = _seed_sync(mysql_sync_session)
        with pytest.raises(ValueError, match="不允许置空"):
            _BuggySyncDAL.update_only_set_by_id(mysql_sync_session, eid, _migration_cu_sync(), none_policy="forbid")

    def test_unset_field_not_in_dump(self, mysql_sync_session: Session) -> None:
        eid = _seed_sync(mysql_sync_session)
        before = _raw_update_dt_sync(mysql_sync_session, "buggy_update_sync", eid)
        _BuggySyncDAL.update_only_set_by_id(mysql_sync_session, eid, _BuggySyncCU(user_id=1, update_operator_id=9))
        mysql_sync_session.flush()
        assert _raw_update_dt_sync(mysql_sync_session, "buggy_update_sync", eid) == before


class TestMysql57ZeroDateReproduction:
    """MySQL 5.7 非严格 sql_mode: allow → zero-date; ignore → 保留."""

    @pytest.mark.parametrize("style", ["setattr", "dot"])
    def test_oracle_assign_none_zero_date(self, mysql57_sync_session: Session, style: AssignStyle) -> None:
        _set_sql_mode_sync(mysql57_sync_session, MYSQL_SQL_MODE_NONSTRICT)
        eid = _seed_sync(mysql57_sync_session)
        entity = mysql57_sync_session.get(_BuggySyncTable, eid)
        assert entity is not None
        oracle_flush_assign_none(mysql57_sync_session, entity, "update_datetime", style=style)
        mysql57_sync_session.commit()
        assert _cast_update_dt_sync(mysql57_sync_session, "buggy_update_sync", eid).startswith("0000-00-00")

    def test_sync_dal_allow_zero_date(self, mysql57_sync_session: Session) -> None:
        _set_sql_mode_sync(mysql57_sync_session, MYSQL_SQL_MODE_NONSTRICT)
        eid = _seed_sync(mysql57_sync_session)
        _BuggySyncDAL.update_only_set_by_id(mysql57_sync_session, eid, _migration_cu_sync())
        mysql57_sync_session.commit()
        assert _cast_update_dt_sync(mysql57_sync_session, "buggy_update_sync", eid).startswith("0000-00-00")

    def test_sync_dal_ignore_preserves(self, mysql57_sync_session: Session) -> None:
        _set_sql_mode_sync(mysql57_sync_session, MYSQL_SQL_MODE_NONSTRICT)
        eid = _seed_sync(mysql57_sync_session)
        before = _raw_update_dt_sync(mysql57_sync_session, "buggy_update_sync", eid)
        _BuggySyncDAL.update_only_set_by_id(mysql57_sync_session, eid, _migration_cu_sync(), none_policy="ignore")
        mysql57_sync_session.commit()
        assert _raw_update_dt_sync(mysql57_sync_session, "buggy_update_sync", eid) == before

    @pytest.mark.asyncio
    async def test_async_dal_allow_zero_date(self, mysql57_async_session: AsyncSession) -> None:
        await _set_sql_mode_async(mysql57_async_session, MYSQL_SQL_MODE_NONSTRICT)
        eid = await _seed_async(mysql57_async_session)
        await _BuggyAsyncDAL.update_only_set_by_id(mysql57_async_session, eid, _migration_cu_async())
        await mysql57_async_session.commit()
        assert (await _cast_update_dt_async(mysql57_async_session, "buggy_update_async", eid)).startswith("0000-00-00")

    @pytest.mark.asyncio
    async def test_async_dal_ignore_preserves(self, mysql57_async_session: AsyncSession) -> None:
        await _set_sql_mode_async(mysql57_async_session, MYSQL_SQL_MODE_NONSTRICT)
        eid = await _seed_async(mysql57_async_session)
        before = await _raw_update_dt_async(mysql57_async_session, "buggy_update_async", eid)
        await _BuggyAsyncDAL.update_only_set_by_id(mysql57_async_session, eid, _migration_cu_async(), none_policy="ignore")
        await mysql57_async_session.commit()
        assert await _raw_update_dt_async(mysql57_async_session, "buggy_update_async", eid) == before


class TestMysql8StrictNoneDatetime:
    """MySQL 8 严格模式: allow 失败; ignore 保留."""

    def test_sync_dal_allow_raises(self, mysql8_sync_session: Session) -> None:
        _set_sql_mode_sync(mysql8_sync_session, MYSQL_SQL_MODE_STRICT)
        eid = _seed_sync(mysql8_sync_session)
        with pytest.raises(_STRICT_WRITE_ERRORS):
            _BuggySyncDAL.update_only_set_by_id(mysql8_sync_session, eid, _migration_cu_sync())
            mysql8_sync_session.flush()

    def test_sync_dal_ignore_preserves(self, mysql8_sync_session: Session) -> None:
        _set_sql_mode_sync(mysql8_sync_session, MYSQL_SQL_MODE_STRICT)
        eid = _seed_sync(mysql8_sync_session)
        before = _raw_update_dt_sync(mysql8_sync_session, "buggy_update_sync", eid)
        _BuggySyncDAL.update_only_set_by_id(mysql8_sync_session, eid, _migration_cu_sync(), none_policy="ignore")
        mysql8_sync_session.commit()
        assert _raw_update_dt_sync(mysql8_sync_session, "buggy_update_sync", eid) == before

    @pytest.mark.asyncio
    async def test_async_dal_allow_raises(self, mysql8_async_session: AsyncSession) -> None:
        await _set_sql_mode_async(mysql8_async_session, MYSQL_SQL_MODE_STRICT)
        eid = await _seed_async(mysql8_async_session)
        with pytest.raises(_STRICT_WRITE_ERRORS):
            await _BuggyAsyncDAL.update_only_set_by_id(mysql8_async_session, eid, _migration_cu_async())
            await mysql8_async_session.flush()

    @pytest.mark.asyncio
    async def test_async_dal_ignore_preserves(self, mysql8_async_session: AsyncSession) -> None:
        await _set_sql_mode_async(mysql8_async_session, MYSQL_SQL_MODE_STRICT)
        eid = await _seed_async(mysql8_async_session)
        before = await _raw_update_dt_async(mysql8_async_session, "buggy_update_async", eid)
        await _BuggyAsyncDAL.update_only_set_by_id(mysql8_async_session, eid, _migration_cu_async(), none_policy="ignore")
        await mysql8_async_session.commit()
        assert await _raw_update_dt_async(mysql8_async_session, "buggy_update_async", eid) == before
