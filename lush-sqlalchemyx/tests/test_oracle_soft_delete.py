"""软删除 oracle 对拍 — DAL 行为须与独立 Core SQL 期望一致."""

from __future__ import annotations

import datetime
from collections.abc import Generator
from pathlib import Path
from typing import Any, ClassVar

import pytest
import sqlalchemy as sa
import yaml
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.pool import NullPool

from lush_sqlalchemyx.base.dal import (
    BaseCU,
    BaseDTO,
    BasicSyncBaseTable,
    FieldIsDeleteSoftDeleteTableMixin,
    SoftDeleteTableMixin,
    SyncBaseDAL,
    SyncSqlATableBase,
    setup_dal_hooks,
)
from lush_sqlalchemyx.mgrs.mysql.sync_manager import SyncMySQLManager
from tests.oracle.soft_delete import (
    oracle_count_visible_rows,
    oracle_is_soft_deleted_row,
    oracle_select_raw_by_id,
    oracle_select_visible_by_id,
)

TEST_CONFIG_PATH = Path(__file__).with_name("test_config.yaml")


def _load_sync_sqlite_uri() -> tuple[str, Path]:
    with TEST_CONFIG_PATH.open(encoding="utf-8") as f:
        config: dict[str, Any] = yaml.safe_load(f)
    mysql_cfg: dict[str, Any] = config.get("MYSQLDB", {})
    sqlite_rel = mysql_cfg.get("TEST_SQLITE_PATH", ".tmp/lush_sqlalchemyx_test.db")
    sqlite_path = (TEST_CONFIG_PATH.parent / sqlite_rel).resolve()
    sqlite_path = sqlite_path.with_name("oracle_" + sqlite_path.name)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{sqlite_path}", sqlite_path


@pytest.fixture
def sync_manager() -> Generator[SyncMySQLManager, None, None]:
    uri, sqlite_path = _load_sync_sqlite_uri()
    manager = SyncMySQLManager(uri, poolclass=NullPool, connect_args={"check_same_thread": False})
    try:
        SyncSqlATableBase.metadata.create_all(manager.engine, checkfirst=True)
        yield manager
    finally:
        manager.close()
        if sqlite_path.exists():
            sqlite_path.unlink()


@pytest.fixture
def sync_session(sync_manager: SyncMySQLManager) -> Generator[Session, None, None]:
    with sync_manager.got_manual_session() as session:
        yield session


class _OracleStdTable(BasicSyncBaseTable, FieldIsDeleteSoftDeleteTableMixin):
    __tablename__ = "oracle_std_soft_delete"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(50), nullable=False)


class _OracleStdCU(BaseCU["_OracleStdTable"]):
    _Table: ClassVar[type[_OracleStdTable]] = _OracleStdTable
    name: str = ""


class _OracleStdDTO(BaseDTO[_OracleStdCU]):
    _CU: ClassVar[type[_OracleStdCU]] = _OracleStdCU
    id: int
    name: str = ""


class _OracleStdDAL(SyncBaseDAL[_OracleStdTable, _OracleStdDTO, _OracleStdCU]):
    _Table = _OracleStdTable
    _DTO = _OracleStdDTO
    _CU = _OracleStdCU


class _OracleCustomTable(BasicSyncBaseTable, SoftDeleteTableMixin):
    __tablename__ = "oracle_custom_soft_delete"

    __soft_delete_column__ = "deleted_at"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(sa.DateTime, nullable=True, default=None)

    @property
    def is_soft_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        self.deleted_at = datetime.datetime.now()

    def soft_undelete(self) -> None:
        self.deleted_at = None

    @classmethod
    def soft_delete_loader_criteria(cls) -> Any:
        return cls.deleted_at.is_(None)


class _OracleCustomCU(BaseCU["_OracleCustomTable"]):
    _Table: ClassVar[type[_OracleCustomTable]] = _OracleCustomTable
    name: str = ""


class _OracleCustomDTO(BaseDTO[_OracleCustomCU]):
    _CU: ClassVar[type[_OracleCustomCU]] = _OracleCustomCU
    id: int
    name: str = ""


class _OracleCustomDAL(SyncBaseDAL[_OracleCustomTable, _OracleCustomDTO, _OracleCustomCU]):
    _Table = _OracleCustomTable
    _DTO = _OracleCustomDTO
    _CU = _OracleCustomCU


@pytest.fixture(autouse=True)
def _ensure_hooks() -> None:
    setup_dal_hooks()


class TestSoftDeleteOracleStd:
    """标准 is_delete 列: DAL vs Core ``WHERE is_delete = 0``."""

    def test_get_by_id_matches_core_visible(self, sync_session: Session) -> None:
        entity = _OracleStdDAL.create(sync_session, _OracleStdCU(name="oracle-std"))
        sync_session.flush()
        eid = entity.id

        dal_result = _OracleStdDAL.get_by_id(sync_session, eid)
        core_row = oracle_select_visible_by_id(sync_session, _OracleStdTable, eid, style="is_delete")
        assert dal_result is not None
        assert core_row is not None
        assert dal_result.name == core_row["name"]

        _OracleStdDAL.delete_by_id(sync_session, eid)
        sync_session.flush()

        assert _OracleStdDAL.get_by_id(sync_session, eid) is None
        assert oracle_select_visible_by_id(sync_session, _OracleStdTable, eid, style="is_delete") is None

        raw = oracle_select_raw_by_id(sync_session, _OracleStdTable, eid)
        assert raw is not None
        assert oracle_is_soft_deleted_row(raw, style="is_delete") is True

    def test_select_visibility_matches_core_count(self, sync_session: Session) -> None:
        active = _OracleStdDAL.create(sync_session, _OracleStdCU(name="active"))
        doomed = _OracleStdDAL.create(sync_session, _OracleStdCU(name="doomed"))
        sync_session.flush()

        _OracleStdDAL.delete_by_id(sync_session, doomed.id)
        sync_session.flush()

        assert oracle_count_visible_rows(sync_session, _OracleStdTable, style="is_delete") == 1
        assert oracle_select_visible_by_id(sync_session, _OracleStdTable, active.id, style="is_delete") is not None
        assert oracle_select_visible_by_id(sync_session, _OracleStdTable, doomed.id, style="is_delete") is None


class TestSoftDeleteOracleCustom:
    """自定义 deleted_at: DAL vs Core ``WHERE deleted_at IS NULL``."""

    def test_active_row_visible_in_core_select(self, sync_session: Session) -> None:
        entity = _OracleCustomTable(name="custom-active")
        sync_session.add(entity)
        sync_session.flush()

        row = oracle_select_visible_by_id(sync_session, _OracleCustomTable, entity.id, style="deleted_at")
        assert row is not None
        assert row["name"] == "custom-active"

    def test_get_by_id_matches_core_after_soft_delete(self, sync_session: Session) -> None:
        entity = _OracleCustomTable(name="custom-del")
        sync_session.add(entity)
        sync_session.flush()
        eid = entity.id

        entity.soft_delete()
        sync_session.flush()

        assert _OracleCustomDAL.get_by_id(sync_session, eid) is None
        assert oracle_select_visible_by_id(sync_session, _OracleCustomTable, eid, style="deleted_at") is None

        raw = oracle_select_raw_by_id(sync_session, _OracleCustomTable, eid)
        assert raw is not None
        assert oracle_is_soft_deleted_row(raw, style="deleted_at") is True

    def test_orm_select_loader_matches_core(self, sync_session: Session) -> None:
        active = _OracleCustomTable(name="loader-active")
        doomed = _OracleCustomTable(name="loader-doomed")
        sync_session.add_all([active, doomed])
        sync_session.flush()
        doomed.soft_delete()
        sync_session.flush()

        orm_found = sync_session.execute(sa.select(_OracleCustomTable).where(_OracleCustomTable.id == active.id)).scalar_one_or_none()
        orm_hidden = sync_session.execute(sa.select(_OracleCustomTable).where(_OracleCustomTable.id == doomed.id)).scalar_one_or_none()

        assert orm_found is not None
        assert orm_hidden is None
        assert oracle_select_visible_by_id(sync_session, _OracleCustomTable, active.id, style="deleted_at") is not None
        assert oracle_select_visible_by_id(sync_session, _OracleCustomTable, doomed.id, style="deleted_at") is None
        assert oracle_count_visible_rows(sync_session, _OracleCustomTable, style="deleted_at") == 1
