"""自定义 ``_pk_attr`` 冒烟测试 (sync + async)."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from typing import ClassVar

import pytest
import sqlalchemy as sa
from pydantic import ConfigDict
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from lush_sqlalchemyx.base.dal import (
    AsyncBaseDAL,
    BaseCU,
    BaseDTO,
    BasicAsyncBaseTable,
    BasicSyncBaseTable,
    SyncBaseDAL,
    pk_field_cu_config,
    setup_dal_hooks,
)

setup_dal_hooks()


class _CustomPkSyncTable(BasicSyncBaseTable):
    __tablename__ = "custom_pk_sync_user"
    user_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(50), nullable=False)


class _CustomPkSyncCU(BaseCU["_CustomPkSyncTable"]):
    _Table: ClassVar[type[_CustomPkSyncTable]] = _CustomPkSyncTable
    cu_config = pk_field_cu_config("user_id")
    user_id: int | None = None
    name: str


class _CustomPkSyncDTO(BaseDTO[_CustomPkSyncCU]):
    _CU: ClassVar[type[_CustomPkSyncCU]] = _CustomPkSyncCU
    user_id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class _CustomPkSyncDAL(SyncBaseDAL[_CustomPkSyncTable, _CustomPkSyncDTO, _CustomPkSyncCU]):
    _Table = _CustomPkSyncTable
    _DTO = _CustomPkSyncDTO
    _CU = _CustomPkSyncCU
    _pk_attr = "user_id"


class _CustomPkAsyncTable(BasicAsyncBaseTable):
    __tablename__ = "custom_pk_async_user"
    user_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(50), nullable=False)


class _CustomPkAsyncCU(BaseCU["_CustomPkAsyncTable"]):
    _Table: ClassVar[type[_CustomPkAsyncTable]] = _CustomPkAsyncTable
    cu_config = pk_field_cu_config("user_id")
    user_id: int | None = None
    name: str


class _CustomPkAsyncDTO(BaseDTO[_CustomPkAsyncCU]):
    _CU: ClassVar[type[_CustomPkAsyncCU]] = _CustomPkAsyncCU
    user_id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class _CustomPkAsyncDAL(AsyncBaseDAL[_CustomPkAsyncTable, _CustomPkAsyncDTO, _CustomPkAsyncCU]):
    _Table = _CustomPkAsyncTable
    _DTO = _CustomPkAsyncDTO
    _CU = _CustomPkAsyncCU
    _pk_attr = "user_id"


@pytest.fixture
def custom_pk_sync_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    BasicSyncBaseTable.metadata.create_all(engine, tables=[_CustomPkSyncTable.__table__])
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        yield session
    engine.dispose()


@pytest.fixture
async def custom_pk_async_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: BasicAsyncBaseTable.metadata.create_all(sync_conn, tables=[_CustomPkAsyncTable.__table__]))
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
    await engine.dispose()


class TestCustomPkAttrSync:
    def test_get_update_batch(self, custom_pk_sync_session: Session) -> None:
        entity = _CustomPkSyncDAL.create(custom_pk_sync_session, _CustomPkSyncCU(name="alice"))
        assert entity.user_id is not None
        got = _CustomPkSyncDAL.get_by_id(custom_pk_sync_session, entity.user_id)
        assert got is not None
        assert got.name == "alice"

        updated = _CustomPkSyncDAL.update_only_set_by_id(
            custom_pk_sync_session,
            entity.user_id,
            _CustomPkSyncCU(name="bob"),
        )
        assert updated is not None
        assert updated.name == "bob"

        batch = _CustomPkSyncDAL.batch_get_id__entity(custom_pk_sync_session, [entity.user_id])
        assert entity.user_id in batch

        n = _CustomPkSyncDAL.batch_update_by_ids(
            custom_pk_sync_session,
            entity_ids=[entity.user_id],
            update_data={_CustomPkSyncTable.name: "carol"},
        )
        assert n == 1
        refreshed = _CustomPkSyncDAL.get_by_id(custom_pk_sync_session, entity.user_id)
        assert refreshed is not None
        assert refreshed.name == "carol"


class TestCustomPkAttrAsync:
    async def test_get_update_batch(self, custom_pk_async_session: AsyncSession) -> None:
        entity = await _CustomPkAsyncDAL.create(custom_pk_async_session, _CustomPkAsyncCU(name="alice"))
        assert entity.user_id is not None
        got = await _CustomPkAsyncDAL.get_by_id(custom_pk_async_session, entity.user_id)
        assert got is not None
        assert got.name == "alice"

        updated = await _CustomPkAsyncDAL.update_only_set_by_id(
            custom_pk_async_session,
            entity.user_id,
            _CustomPkAsyncCU(name="bob"),
        )
        assert updated is not None
        assert updated.name == "bob"

        batch = await _CustomPkAsyncDAL.batch_get_id__entity(custom_pk_async_session, [entity.user_id])
        assert entity.user_id in batch

        n = await _CustomPkAsyncDAL.batch_update_by_ids(
            custom_pk_async_session,
            entity_ids=[entity.user_id],
            update_data={_CustomPkAsyncTable.name: "carol"},
        )
        assert n == 1
        refreshed = await _CustomPkAsyncDAL.get_by_id(custom_pk_async_session, entity.user_id)
        assert refreshed is not None
        assert refreshed.name == "carol"
