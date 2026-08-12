"""async cu_config / 1:1 扩展表 / Dynamic — 与裸 Async Core oracle 对拍."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import ClassVar

import pytest
import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

from lush_sqlalchemyx.base.dal import (
    EXTEND_TABLE_CU_CONFIG,
    AsyncBaseDAL,
    BaseCU,
    BaseDTO,
    BasicAsyncBaseTable,
    DynamicAsyncDAL,
    DynamicTableConfig,
    TableRef,
    setup_dal_hooks,
)
from tests.oracle.extend_table import (
    async_oracle_count_rows,
    async_oracle_insert_extend_row,
    async_oracle_insert_main_row,
    async_oracle_select_raw_sql,
    async_oracle_select_row_by_id,
    async_oracle_update_extend_row,
)

setup_dal_hooks()


class _AsyncMainJobTable(BasicAsyncBaseTable):
    __tablename__ = "async_cu_config_main_job"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    stage: Mapped[str] = mapped_column(sa.String(20), nullable=False)


class _AsyncExtendJobTable(BasicAsyncBaseTable):
    __tablename__ = "async_cu_config_extend_job"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=False)
    report_name: Mapped[str] = mapped_column(sa.String(64), nullable=False)


class _AsyncMainJobCU(BaseCU["_AsyncMainJobTable"]):
    _Table: ClassVar[type[_AsyncMainJobTable]] = _AsyncMainJobTable
    stage: str


class _AsyncMainJobDTO(BaseDTO[_AsyncMainJobCU]):
    _CU: ClassVar[type[_AsyncMainJobCU]] = _AsyncMainJobCU
    id: int
    stage: str
    model_config = ConfigDict(from_attributes=True)


class _AsyncExtendJobCU(BaseCU["_AsyncExtendJobTable"]):
    _Table: ClassVar[type[_AsyncExtendJobTable]] = _AsyncExtendJobTable
    cu_config = EXTEND_TABLE_CU_CONFIG
    id: int
    report_name: str


class _AsyncExtendJobDTO(BaseDTO[_AsyncExtendJobCU]):
    _CU: ClassVar[type[_AsyncExtendJobCU]] = _AsyncExtendJobCU
    id: int
    report_name: str
    model_config = ConfigDict(from_attributes=True)


class _AsyncMainJobDAL(AsyncBaseDAL[_AsyncMainJobTable, _AsyncMainJobDTO, _AsyncMainJobCU]):
    _Table = _AsyncMainJobTable
    _DTO = _AsyncMainJobDTO
    _CU = _AsyncMainJobCU


class _AsyncExtendJobDAL(AsyncBaseDAL[_AsyncExtendJobTable, _AsyncExtendJobDTO, _AsyncExtendJobCU]):
    _Table = _AsyncExtendJobTable
    _DTO = _AsyncExtendJobDTO
    _CU = _AsyncExtendJobCU


@pytest.fixture()
async def async_orm_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: BasicAsyncBaseTable.metadata.create_all(
                sync_conn,
                tables=[_AsyncMainJobTable.__table__, _AsyncExtendJobTable.__table__],
            )
        )
    SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
    await engine.dispose()


class TestAsyncOrmExtendTableOraclePair:
    async def test_paired_create_matches_oracle(self, async_orm_session: AsyncSession) -> None:
        oracle_id = await async_oracle_insert_main_row(async_orm_session, _AsyncMainJobTable, stage="oracle-pending")
        await async_oracle_insert_extend_row(
            async_orm_session,
            _AsyncExtendJobTable,
            entity_id=oracle_id,
            report_name="oracle-r1",
        )
        oracle_row = await async_oracle_select_row_by_id(async_orm_session, _AsyncExtendJobTable, oracle_id)
        assert oracle_row == {"id": oracle_id, "report_name": "oracle-r1"}

        main = await _AsyncMainJobDAL.ret_dto_after_create(async_orm_session, _AsyncMainJobCU(stage="dal-pending"))
        extend = await _AsyncExtendJobDAL.ret_dto_after_create(
            async_orm_session,
            _AsyncExtendJobCU(id=main.id, report_name="dal-r1"),
        )
        dal_row = await async_oracle_select_row_by_id(async_orm_session, _AsyncExtendJobTable, main.id)
        assert extend.id == main.id
        assert dal_row == {"id": main.id, "report_name": "dal-r1"}
        assert await async_oracle_count_rows(async_orm_session, _AsyncExtendJobTable) == 2

    async def test_update_ignores_cu_id_matches_oracle(self, async_orm_session: AsyncSession) -> None:
        main = await _AsyncMainJobDAL.ret_dto_after_create(async_orm_session, _AsyncMainJobCU(stage="pending"))
        await _AsyncExtendJobDAL.ret_dto_after_create(
            async_orm_session,
            _AsyncExtendJobCU(id=main.id, report_name="r1"),
        )

        oracle_rc = await async_oracle_update_extend_row(
            async_orm_session,
            _AsyncExtendJobTable,
            main.id,
            report_name="oracle-r2",
        )
        assert oracle_rc == 1
        assert await async_oracle_select_row_by_id(async_orm_session, _AsyncExtendJobTable, main.id) == {
            "id": main.id,
            "report_name": "oracle-r2",
        }
        assert await async_oracle_select_row_by_id(async_orm_session, _AsyncExtendJobTable, 999) is None

        updated = await _AsyncExtendJobDAL.ret_dto_after_update_by_id(
            async_orm_session,
            main.id,
            _AsyncExtendJobCU(id=999, report_name="dal-r3"),
        )
        assert updated is not None
        assert updated.id == main.id
        assert updated.report_name == "dal-r3"
        assert await async_oracle_select_row_by_id(async_orm_session, _AsyncExtendJobTable, main.id) == {
            "id": main.id,
            "report_name": "dal-r3",
        }
        assert await async_oracle_select_row_by_id(async_orm_session, _AsyncExtendJobTable, 999) is None
        assert await async_oracle_count_rows(async_orm_session, _AsyncExtendJobTable) == 1

    async def test_update_full_and_partial_ignore_id(self, async_orm_session: AsyncSession) -> None:
        main = await _AsyncMainJobDAL.ret_dto_after_create(async_orm_session, _AsyncMainJobCU(stage="pending"))
        await _AsyncExtendJobDAL.create(async_orm_session, _AsyncExtendJobCU(id=main.id, report_name="r1"))

        full = await _AsyncExtendJobDAL.update_full_by_id(
            async_orm_session,
            main.id,
            _AsyncExtendJobCU(id=888, report_name="full"),
        )
        assert full is not None
        assert full.id == main.id
        row = await async_oracle_select_row_by_id(async_orm_session, _AsyncExtendJobTable, main.id)
        assert row is not None
        assert row["report_name"] == "full"

        partial = await _AsyncExtendJobDAL.update_partial_by_id(
            async_orm_session,
            main.id,
            _AsyncExtendJobCU(id=777, report_name="partial"),
        )
        assert partial is not None
        assert partial.id == main.id
        row2 = await async_oracle_select_row_by_id(async_orm_session, _AsyncExtendJobTable, main.id)
        assert row2 is not None
        assert row2["report_name"] == "partial"


class _DynExtendDTO(BaseModel):
    id: int
    report_name: str


class _DynExtendCU(BaseModel):
    id: int
    report_name: str


@pytest.fixture()
async def async_dyn_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(sa.text("CREATE TABLE async_dyn_extend_job (id INTEGER PRIMARY KEY NOT NULL, report_name VARCHAR(64) NOT NULL)"))
    SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
    await engine.dispose()


class TestAsyncDynamicExcludePkOnCreateOracle:
    async def test_exclude_pk_false_inserts_explicit_pk(self, async_dyn_session: AsyncSession) -> None:
        ref = TableRef(
            table_name="async_dyn_extend_job",
            config=DynamicTableConfig(exclude_pk_on_create=False),
            _dto_class=_DynExtendDTO,
        )
        dal = DynamicAsyncDAL(ref, _DynExtendDTO)
        dto = await dal.create(_DynExtendCU(id=7, report_name="x"), session=async_dyn_session)
        assert dto.id == 7

        row = await async_oracle_select_raw_sql(
            async_dyn_session,
            "SELECT id, report_name FROM async_dyn_extend_job WHERE id = :id",
            {"id": 7},
        )
        assert row == {"id": 7, "report_name": "x"}

    async def test_default_exclude_pk_ignores_cu_id(self, async_dyn_session: AsyncSession) -> None:
        ref = TableRef.of("async_dyn_extend_job", _DynExtendDTO)
        dal = DynamicAsyncDAL(ref, _DynExtendDTO)
        dto = await dal.create(_DynExtendCU(id=99, report_name="auto"), session=async_dyn_session)
        assert dto.id != 99
        missing = await async_oracle_select_raw_sql(
            async_dyn_session,
            "SELECT id FROM async_dyn_extend_job WHERE id = :id",
            {"id": 99},
        )
        assert missing is None

    async def test_update_never_rewrites_pk(self, async_dyn_session: AsyncSession) -> None:
        ref = TableRef(
            table_name="async_dyn_extend_job",
            config=DynamicTableConfig(exclude_pk_on_create=False),
            _dto_class=_DynExtendDTO,
        )
        dal = DynamicAsyncDAL(ref, _DynExtendDTO)
        await dal.create(_DynExtendCU(id=5, report_name="a"), session=async_dyn_session)

        rc = await dal.update_by_id(5, _DynExtendCU(id=999, report_name="b"), session=async_dyn_session)
        assert rc == 1
        got = await dal.get_by_id(5, session=async_dyn_session)
        assert got is not None
        assert got.id == 5
        assert got.report_name == "b"
        assert await dal.get_by_id(999, session=async_dyn_session) is None
        row = await async_oracle_select_raw_sql(
            async_dyn_session,
            "SELECT id, report_name FROM async_dyn_extend_job WHERE id = :id",
            {"id": 5},
        )
        assert row == {"id": 5, "report_name": "b"}
