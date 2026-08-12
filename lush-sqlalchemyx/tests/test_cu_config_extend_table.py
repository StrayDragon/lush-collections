"""cu_config / 1:1 扩展表 / Dynamic exclude_pk_on_create — 含 oracle Core 对拍."""

from __future__ import annotations

from collections.abc import Generator
from typing import ClassVar

import pytest
import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from lush_sqlalchemyx.base.dal import (
    EXTEND_TABLE_CU_CONFIG,
    BaseCU,
    BaseCUConfigDict,
    BaseDTO,
    BasicSyncBaseTable,
    DynamicSyncDAL,
    DynamicTableConfig,
    SyncBaseDAL,
    TableRef,
    setup_dal_hooks,
)
from tests.oracle.extend_table import (
    oracle_count_rows,
    oracle_insert_extend_row,
    oracle_insert_main_row,
    oracle_select_row_by_id,
    oracle_update_extend_row,
)

setup_dal_hooks()


class _MainJobTable(BasicSyncBaseTable):
    __tablename__ = "cu_config_main_job"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    stage: Mapped[str] = mapped_column(sa.String(20), nullable=False)


class _ExtendJobTable(BasicSyncBaseTable):
    __tablename__ = "cu_config_extend_job"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=False)
    report_name: Mapped[str] = mapped_column(sa.String(64), nullable=False)


class _MainJobCU(BaseCU["_MainJobTable"]):
    _Table: ClassVar[type[_MainJobTable]] = _MainJobTable
    stage: str


class _MainJobDTO(BaseDTO[_MainJobCU]):
    _CU: ClassVar[type[_MainJobCU]] = _MainJobCU
    id: int
    stage: str
    model_config = ConfigDict(from_attributes=True)


class _ExtendJobCU(BaseCU["_ExtendJobTable"]):
    _Table: ClassVar[type[_ExtendJobTable]] = _ExtendJobTable
    cu_config = EXTEND_TABLE_CU_CONFIG
    id: int
    report_name: str


class _ExtendJobDTO(BaseDTO[_ExtendJobCU]):
    _CU: ClassVar[type[_ExtendJobCU]] = _ExtendJobCU
    id: int
    report_name: str
    model_config = ConfigDict(from_attributes=True)


class _MainJobDAL(SyncBaseDAL[_MainJobTable, _MainJobDTO, _MainJobCU]):
    _Table = _MainJobTable
    _DTO = _MainJobDTO
    _CU = _MainJobCU


class _ExtendJobDAL(SyncBaseDAL[_ExtendJobTable, _ExtendJobDTO, _ExtendJobCU]):
    _Table = _ExtendJobTable
    _DTO = _ExtendJobDTO
    _CU = _ExtendJobCU


class _DefaultIdCU(BaseCU["_ExtendJobTable"]):
    """故意不设 EXTEND_TABLE_CU_CONFIG — create 应丢掉 id."""

    _Table: ClassVar[type[_ExtendJobTable]] = _ExtendJobTable
    id: int = 0
    report_name: str


class _DefaultIdDAL(SyncBaseDAL[_ExtendJobTable, _ExtendJobDTO, _DefaultIdCU]):
    _Table = _ExtendJobTable
    _DTO = _ExtendJobDTO
    _CU = _DefaultIdCU


@pytest.fixture()
def orm_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    BasicSyncBaseTable.metadata.create_all(
        engine,
        tables=[_MainJobTable.__table__, _ExtendJobTable.__table__],
    )
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        yield session


class TestOrmExtendTableOraclePair:
    """DAL 与裸 Core oracle 对拍."""

    def test_paired_create_matches_oracle(self, orm_session: Session) -> None:
        oracle_id = oracle_insert_main_row(orm_session, _MainJobTable, stage="oracle-pending")
        oracle_insert_extend_row(
            orm_session,
            _ExtendJobTable,
            entity_id=oracle_id,
            report_name="oracle-r1",
        )
        oracle_row = oracle_select_row_by_id(orm_session, _ExtendJobTable, oracle_id)
        assert oracle_row == {"id": oracle_id, "report_name": "oracle-r1"}

        main = _MainJobDAL.ret_dto_after_create(orm_session, _MainJobCU(stage="dal-pending"))
        extend = _ExtendJobDAL.ret_dto_after_create(
            orm_session,
            _ExtendJobCU(id=main.id, report_name="dal-r1"),
        )
        dal_row = oracle_select_row_by_id(orm_session, _ExtendJobTable, main.id)
        assert extend.id == main.id
        assert dal_row == {"id": main.id, "report_name": "dal-r1"}
        assert oracle_count_rows(orm_session, _ExtendJobTable) == 2

    def test_update_ignores_cu_id_matches_oracle(self, orm_session: Session) -> None:
        main = _MainJobDAL.ret_dto_after_create(orm_session, _MainJobCU(stage="pending"))
        _ExtendJobDAL.ret_dto_after_create(
            orm_session,
            _ExtendJobCU(id=main.id, report_name="r1"),
        )

        oracle_rc = oracle_update_extend_row(
            orm_session,
            _ExtendJobTable,
            main.id,
            report_name="oracle-r2",
        )
        assert oracle_rc == 1
        assert oracle_select_row_by_id(orm_session, _ExtendJobTable, main.id) == {
            "id": main.id,
            "report_name": "oracle-r2",
        }
        # 误传 id=999 不得改 PK
        assert oracle_select_row_by_id(orm_session, _ExtendJobTable, 999) is None

        updated = _ExtendJobDAL.ret_dto_after_update_by_id(
            orm_session,
            main.id,
            _ExtendJobCU(id=999, report_name="dal-r3"),
        )
        assert updated is not None
        assert updated.id == main.id
        assert updated.report_name == "dal-r3"
        assert oracle_select_row_by_id(orm_session, _ExtendJobTable, main.id) == {
            "id": main.id,
            "report_name": "dal-r3",
        }
        assert oracle_select_row_by_id(orm_session, _ExtendJobTable, 999) is None
        assert oracle_count_rows(orm_session, _ExtendJobTable) == 1

    def test_update_full_and_partial_ignore_id(self, orm_session: Session) -> None:
        main = _MainJobDAL.ret_dto_after_create(orm_session, _MainJobCU(stage="pending"))
        _ExtendJobDAL.create(orm_session, _ExtendJobCU(id=main.id, report_name="r1"))

        full = _ExtendJobDAL.update_full_by_id(
            orm_session,
            main.id,
            _ExtendJobCU(id=888, report_name="full"),
        )
        assert full is not None
        assert full.id == main.id
        assert oracle_select_row_by_id(orm_session, _ExtendJobTable, main.id)["report_name"] == "full"

        partial = _ExtendJobDAL.update_partial_by_id(
            orm_session,
            main.id,
            _ExtendJobCU(id=777, report_name="partial"),
        )
        assert partial is not None
        assert partial.id == main.id
        assert oracle_select_row_by_id(orm_session, _ExtendJobTable, main.id)["report_name"] == "partial"

    def test_default_cu_config_drops_id_on_create(self, orm_session: Session) -> None:
        """未设置 EXTEND_TABLE_CU_CONFIG 时, to_orm_model / dump 丢掉 id."""
        assert _DefaultIdCU.resolve_cu_config()["to_orm_exclude"] == frozenset({"id"})
        entity = _DefaultIdCU(id=123, report_name="no-extend-cfg").to_orm_model()
        assert entity.id is None
        assert entity.report_name == "no-extend-cfg"
        dumped = _DefaultIdCU(id=123, report_name="x").model_dump(
            exclude_unset=True,
            exclude=_DefaultIdCU.resolve_cu_config()["to_orm_exclude"],
        )
        assert "id" not in dumped
        assert dumped["report_name"] == "x"


class TestOrmExtendTableCuConfig:
    def test_create_with_shared_pk_and_update_keeps_pk(self, orm_session: Session) -> None:
        main = _MainJobDAL.ret_dto_after_create(orm_session, _MainJobCU(stage="pending"))
        assert main.id > 0

        extend = _ExtendJobDAL.ret_dto_after_create(
            orm_session,
            _ExtendJobCU(id=main.id, report_name="r1"),
        )
        assert extend.id == main.id
        assert extend.report_name == "r1"

        updated = _ExtendJobDAL.ret_dto_after_update_by_id(
            orm_session,
            main.id,
            _ExtendJobCU(id=999, report_name="r2"),
        )
        assert updated is not None
        assert updated.id == main.id
        assert updated.report_name == "r2"

    def test_inline_cu_config_kw_same_as_constant(self, orm_session: Session) -> None:
        class _InlineExtendCU(BaseCU["_ExtendJobTable"]):
            _Table: ClassVar[type[_ExtendJobTable]] = _ExtendJobTable
            cu_config = BaseCUConfigDict(to_orm_exclude=frozenset())
            id: int
            report_name: str

        class _InlineDAL(SyncBaseDAL[_ExtendJobTable, _ExtendJobDTO, _InlineExtendCU]):
            _Table = _ExtendJobTable
            _DTO = _ExtendJobDTO
            _CU = _InlineExtendCU

        main = _MainJobDAL.ret_dto_after_create(orm_session, _MainJobCU(stage="s"))
        dto = _InlineDAL.ret_dto_after_create(
            orm_session,
            _InlineExtendCU(id=main.id, report_name="inline"),
        )
        assert dto.id == main.id
        assert _InlineExtendCU.resolve_cu_config()["update_exclude"] == frozenset({"id"})


class _DynExtendDTO(BaseModel):
    id: int
    report_name: str


class _DynExtendCU(BaseModel):
    id: int
    report_name: str


@pytest.fixture()
def dyn_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE dyn_extend_job (id INTEGER PRIMARY KEY NOT NULL, report_name VARCHAR(64) NOT NULL)"))
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        yield session


class TestDynamicExcludePkOnCreate:
    def test_exclude_pk_on_create_false_inserts_explicit_pk(self, dyn_session: Session) -> None:
        ref = TableRef(
            table_name="dyn_extend_job",
            config=DynamicTableConfig(exclude_pk_on_create=False),
            _dto_class=_DynExtendDTO,
        )
        dal = DynamicSyncDAL(ref, _DynExtendDTO)
        dto = dal.create(_DynExtendCU(id=7, report_name="x"), session=dyn_session)
        assert dto.id == 7
        assert dto.report_name == "x"

        got = dal.get_by_id(7, session=dyn_session)
        assert got is not None
        assert got.id == 7

        # oracle: 物理行存在
        row = (
            dyn_session.execute(
                sa.text("SELECT id, report_name FROM dyn_extend_job WHERE id = :id"),
                {"id": 7},
            )
            .mappings()
            .one()
        )
        assert dict(row) == {"id": 7, "report_name": "x"}

    def test_default_exclude_pk_ignores_cu_id(self, dyn_session: Session) -> None:
        ref = TableRef.of("dyn_extend_job", _DynExtendDTO)
        assert ref.config.exclude_pk_on_create is True
        dal = DynamicSyncDAL(ref, _DynExtendDTO)
        # CU 带 id=99, 但 create dump 排除 pk → SQLite 自分配
        dto = dal.create(_DynExtendCU(id=99, report_name="auto"), session=dyn_session)
        assert dto.id != 99
        assert dto.report_name == "auto"
        assert dyn_session.execute(sa.text("SELECT COUNT(*) FROM dyn_extend_job WHERE id = 99")).scalar_one() == 0

    def test_update_never_rewrites_pk_even_when_create_keeps_pk(self, dyn_session: Session) -> None:
        ref = TableRef(
            table_name="dyn_extend_job",
            config=DynamicTableConfig(exclude_pk_on_create=False),
            _dto_class=_DynExtendDTO,
        )
        dal = DynamicSyncDAL(ref, _DynExtendDTO)
        dal.create(_DynExtendCU(id=5, report_name="a"), session=dyn_session)

        rc = dal.update_by_id(5, _DynExtendCU(id=999, report_name="b"), session=dyn_session)
        assert rc == 1
        got = dal.get_by_id(5, session=dyn_session)
        assert got is not None
        assert got.id == 5
        assert got.report_name == "b"
        assert dal.get_by_id(999, session=dyn_session) is None
        row = dyn_session.execute(sa.text("SELECT id, report_name FROM dyn_extend_job WHERE id = 5")).mappings().one()
        assert dict(row) == {"id": 5, "report_name": "b"}
