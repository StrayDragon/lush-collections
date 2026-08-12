"""主键 `_pk_attr` 与审计列去魔法 — DAL 与 Core oracle 对拍 + UPDATE SQL 断言."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any, ClassVar

import pytest
import sqlalchemy as sa
from pydantic import ConfigDict
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from lush_sqlalchemyx.base.dal import (
    BaseCU,
    BaseDTO,
    BasicSyncBaseTable,
    SyncBaseDAL,
    pk_field_cu_config,
    setup_dal_hooks,
)
from tests.oracle.pk_and_audit import (
    oracle_insert_row,
    oracle_raw_sql_sets_column,
    oracle_select_by_pk,
    oracle_update_by_pk,
    oracle_update_set_clause,
    oracle_update_sets_column,
)

setup_dal_hooks()


class _AuditTable(BasicSyncBaseTable):
    __tablename__ = "oracle_audit_job"
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    update_datetime: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    update_operator_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    version: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, default=0, server_default="0")


class _AuditCU(BaseCU["_AuditTable"]):
    _Table: ClassVar[type[_AuditTable]] = _AuditTable
    name: str
    update_datetime: int | None = None
    update_operator_id: int | None = None


class _AuditDTO(BaseDTO[_AuditCU]):
    _CU: ClassVar[type[_AuditCU]] = _AuditCU
    id: int
    name: str
    update_datetime: int | None = None
    update_operator_id: int | None = None
    version: int
    model_config = ConfigDict(from_attributes=True)


class _AuditDAL(SyncBaseDAL[_AuditTable, _AuditDTO, _AuditCU]):
    _Table = _AuditTable
    _DTO = _AuditDTO
    _CU = _AuditCU


class _CustomPkTable(BasicSyncBaseTable):
    __tablename__ = "oracle_custom_pk_user"
    user_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(50), nullable=False)


class _CustomPkCU(BaseCU["_CustomPkTable"]):
    _Table: ClassVar[type[_CustomPkTable]] = _CustomPkTable
    cu_config = pk_field_cu_config("user_id")
    user_id: int | None = None
    name: str


class _CustomPkDTO(BaseDTO[_CustomPkCU]):
    _CU: ClassVar[type[_CustomPkCU]] = _CustomPkCU
    user_id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class _CustomPkDAL(SyncBaseDAL[_CustomPkTable, _CustomPkDTO, _CustomPkCU]):
    _Table = _CustomPkTable
    _DTO = _CustomPkDTO
    _CU = _CustomPkCU
    _pk_attr = "user_id"


@pytest.fixture
def oracle_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    BasicSyncBaseTable.metadata.create_all(engine, tables=[_AuditTable.__table__, _CustomPkTable.__table__])
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        yield session
    engine.dispose()


class TestAuditNoImplicitWriteOracle:
    def test_batch_update_matches_oracle_and_sql_omits_audit(self, oracle_session: Session) -> None:
        eid = oracle_insert_row(oracle_session, _AuditTable, values={"name": "before", "version": 0})
        oracle_session.commit()

        captured: list[str] = []

        @event.listens_for(oracle_session.bind, "before_cursor_execute")
        def _capture(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:  # noqa: ANN001
            if str(statement).lstrip().upper().startswith("UPDATE"):
                captured.append(str(statement))

        affected = _AuditDAL.batch_update_by_ids(
            oracle_session,
            entity_ids=[eid],
            update_data={_AuditTable.name: "after"},
        )
        assert affected == 1
        oracle_session.commit()

        assert captured, "应捕获到 batch UPDATE SQL"
        assert not oracle_raw_sql_sets_column(captured[-1], "update_datetime")
        assert not oracle_raw_sql_sets_column(captured[-1], "update_operator_id")

        # oracle 显式仅更新 name, 物理行应对齐
        oracle_update_by_pk(oracle_session, _AuditTable, eid, values={"name": "after-oracle"})
        oracle_session.commit()
        dal_row = oracle_select_by_pk(oracle_session, _AuditTable, eid)
        assert dal_row is not None
        assert dal_row["update_datetime"] is None
        assert dal_row["update_operator_id"] is None

        # 再走 DAL 一次后仍保持审计列为 None
        _AuditDAL.batch_update_by_conditions(
            oracle_session,
            whereclause=[_AuditTable.id == eid],
            update_data={_AuditTable.name: "final"},
        )
        oracle_session.commit()
        row = oracle_select_by_pk(oracle_session, _AuditTable, eid)
        assert row is not None
        assert row["name"] == "final"
        assert row["update_datetime"] is None
        assert row["update_operator_id"] is None

    def test_optimistic_lock_sql_omits_update_datetime(self, oracle_session: Session) -> None:
        eid = oracle_insert_row(oracle_session, _AuditTable, values={"name": "v0", "version": 0})
        oracle_session.commit()

        captured: list[Any] = []

        @event.listens_for(oracle_session.bind, "before_cursor_execute")
        def _capture(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:  # noqa: ANN001
            if str(statement).lstrip().upper().startswith("UPDATE"):
                captured.append(statement)

        updated = _AuditDAL.update_only_set_with_optimistic_lock(
            oracle_session,
            eid,
            _AuditCU(name="v1"),
            expected_version=0,
        )
        assert updated is not None
        oracle_session.commit()

        assert captured
        assert not oracle_raw_sql_sets_column(str(captured[-1]), "update_datetime")
        assert not oracle_raw_sql_sets_column(str(captured[-1]), "update_operator_id")

        row = oracle_select_by_pk(oracle_session, _AuditTable, eid)
        assert row is not None
        assert row["name"] == "v1"
        assert row["version"] == 1
        assert row["update_datetime"] is None


class TestCustomPkAttrOracle:
    def test_get_update_batch_match_oracle(self, oracle_session: Session) -> None:
        pk = oracle_insert_row(oracle_session, _CustomPkTable, values={"name": "alice"})
        oracle_session.commit()

        got = _CustomPkDAL.get_by_id(oracle_session, pk)
        assert got is not None
        assert got.name == "alice"
        oracle_row = oracle_select_by_pk(oracle_session, _CustomPkTable, pk, pk_attr="user_id")
        assert oracle_row is not None
        assert oracle_row["name"] == got.name

        _CustomPkDAL.update_only_set_by_id(oracle_session, pk, _CustomPkCU(name="bob"))
        oracle_session.flush()
        after = oracle_select_by_pk(oracle_session, _CustomPkTable, pk, pk_attr="user_id")
        assert after is not None
        assert after["name"] == "bob"

        batch = _CustomPkDAL.batch_get_id__entity(oracle_session, [pk])
        assert pk in batch

        n = _CustomPkDAL.batch_update_by_ids(
            oracle_session,
            entity_ids=[pk],
            update_data={_CustomPkTable.name: "carol"},
        )
        assert n == 1
        oracle_update_by_pk(oracle_session, _CustomPkTable, pk, values={"name": "carol"}, pk_attr="user_id")
        final = oracle_select_by_pk(oracle_session, _CustomPkTable, pk, pk_attr="user_id")
        assert final is not None
        assert final["name"] == "carol"


def test_oracle_helpers_detect_set_columns() -> None:
    stmt = sa.update(_AuditTable).where(_AuditTable.id == 1).values(name="x")
    assert not oracle_update_sets_column(stmt, "update_datetime")
    assert "name" in oracle_update_set_clause(stmt)
