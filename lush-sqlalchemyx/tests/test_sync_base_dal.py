"""Sync DAL tests — mirrors test_base_dal.py for the synchronous API."""

from collections.abc import Generator
from pathlib import Path
from typing import Any, ClassVar

import pytest
import sqlalchemy as sa
import yaml
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import event, text
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.pool import NullPool

from lush_sqlalchemyx.base.dal import (
    BaseCU,
    BaseDTO,
    DBRetryableError,
    FieldMixin,
    ReadOnlySyncBaseDAL,
    ReadOnlySyncBaseTable,
    StdBaseCU,
    StdBaseDTO,
    StdSyncBaseTable,
    SyncBaseDAL,
    SyncSqlATableBase,
    SyncWriteDAL,
    SyncXDALOp,
    sync_temp_set_lock_wait_timeout,
    sync_with_retry,
)
from lush_sqlalchemyx.base.dal._common import (
    READONLY_SESSION_FLAG,
    RetryConfig,
)
from lush_sqlalchemyx.base.dal._sync import BasicSyncBaseTable
from lush_sqlalchemyx.mgrs.mysql.sync_manager import SyncMySQLManager

# ========== Test models ==========


class _SyncTestTable(StdSyncBaseTable):
    __tablename__ = "sync_test_table"

    name: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    status: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, default=1)
    description: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    value: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)


class _SyncSimpleTable(BasicSyncBaseTable):
    __tablename__ = "sync_test_simple"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(50), nullable=False)


class _SyncVersionTable(StdSyncBaseTable):
    __tablename__ = "sync_test_version"

    name: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    value: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, default=0, server_default="0")


class _SyncReadOnlyTable(ReadOnlySyncBaseTable):
    __tablename__ = "sync_test_readonly"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    value: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)


class _SyncTestCU(StdBaseCU["_SyncTestTable"]):
    _Table: ClassVar[type[_SyncTestTable]] = _SyncTestTable
    name: str
    status: int = 1
    description: str | None = None
    value: int = 0


class _SyncSimpleCU(BaseCU["_SyncSimpleTable"]):
    _Table: ClassVar[type[_SyncSimpleTable]] = _SyncSimpleTable
    name: str


class _SyncTestDTO(StdBaseDTO[_SyncTestCU]):
    _CU: ClassVar[type[_SyncTestCU]] = _SyncTestCU
    name: str = Field(...)
    status: int = Field(...)
    description: str | None = Field(None)
    value: int = Field(...)
    model_config = ConfigDict(from_attributes=True)


class _SyncSimpleDTO(BaseDTO[_SyncSimpleCU]):
    _CU: ClassVar[type[_SyncSimpleCU]] = _SyncSimpleCU
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class _SyncVersionCU(StdBaseCU["_SyncVersionTable"]):
    _Table: ClassVar[type[_SyncVersionTable]] = _SyncVersionTable
    name: str
    value: int = 0


class _SyncVersionDTO(StdBaseDTO[_SyncVersionCU]):
    _CU: ClassVar[type[_SyncVersionCU]] = _SyncVersionCU
    name: str
    value: int
    version: int
    model_config = ConfigDict(from_attributes=True)


class _SyncReadOnlyCU(BaseCU["_SyncReadOnlyTable"]):
    _Table: ClassVar[type[_SyncReadOnlyTable]] = _SyncReadOnlyTable
    name: str
    value: int = 0


class _SyncReadOnlyDTO(BaseDTO[_SyncReadOnlyCU]):
    _CU: ClassVar[type[_SyncReadOnlyCU]] = _SyncReadOnlyCU
    id: int
    name: str
    value: int = 0
    model_config = ConfigDict(from_attributes=True)


_SyncReadOnlyDTO._CU = _SyncReadOnlyCU


# ========== DAL classes ==========


class _SyncTestDAL(SyncBaseDAL[_SyncTestTable, _SyncTestDTO, _SyncTestCU]):
    _Table = _SyncTestTable
    _DTO = _SyncTestDTO
    _CU = _SyncTestCU


class _SyncSimpleDAL(SyncBaseDAL[_SyncSimpleTable, _SyncSimpleDTO, _SyncSimpleCU]):
    _Table = _SyncSimpleTable
    _DTO = _SyncSimpleDTO
    _CU = _SyncSimpleCU


class _SyncVersionDAL(SyncBaseDAL[_SyncVersionTable, _SyncVersionDTO, _SyncVersionCU]):
    _Table = _SyncVersionTable
    _DTO = _SyncVersionDTO
    _CU = _SyncVersionCU


class _SyncReadOnlyDAL(ReadOnlySyncBaseDAL[_SyncReadOnlyTable, _SyncReadOnlyDTO]):
    _Table = _SyncReadOnlyTable
    _DTO = _SyncReadOnlyDTO


# ========== Fixtures ==========

TEST_CONFIG_PATH = Path(__file__).with_name("test_config.yaml")


def _load_sync_sqlite_uri() -> tuple[str, Path]:
    with TEST_CONFIG_PATH.open(encoding="utf-8") as f:
        config: dict[str, Any] = yaml.safe_load(f)
    mysql_cfg: dict[str, Any] = config.get("MYSQLDB", {})
    sqlite_rel = mysql_cfg.get("TEST_SQLITE_PATH", ".tmp/lush_sqlalchemyx_test.db")
    sqlite_path = (TEST_CONFIG_PATH.parent / sqlite_rel).resolve()
    sqlite_path = sqlite_path.with_name("sync_" + sqlite_path.name)
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


# ========== Readonly helper ==========


def _create_readonly_test_data(session: Session, name: str, value: int) -> int:
    import lush_sqlalchemyx.base.dal._common as common_mod

    listener = getattr(common_mod, "_CommonModule__prevent_readonly_write", None) or getattr(common_mod, "__prevent_readonly_write", None)

    if listener:
        from sqlalchemy.orm import Session as SyncSession

        event.remove(SyncSession, "before_flush", listener)
        try:
            entity = _SyncReadOnlyTable(name=name, value=value)
            session.add(entity)
            session.flush()
            eid = entity.id
            session.commit()
            return eid
        finally:
            event.listen(SyncSession, "before_flush", listener)
    else:
        entity = _SyncReadOnlyTable(name=name, value=value)
        session.add(entity)
        session.flush()
        eid = entity.id
        session.commit()
        return eid


# ========== Tests ==========


class TestSyncCRUD:
    def test_create_and_get(self, sync_session: Session):
        cu = _SyncTestCU(name="sync-test", status=1, value=42)
        entity = _SyncTestDAL.create(sync_session, cu)
        assert entity.name == "sync-test"
        assert entity.value == 42

        fetched = _SyncTestDAL.get_by_id(sync_session, entity.id)
        assert fetched is not None
        assert fetched.name == "sync-test"

    def test_create_no_refresh(self, sync_session: Session):
        cu = _SyncTestCU(name="no-refresh-create")
        entity = _SyncTestDAL.create(sync_session, cu, need_refresh=False)
        assert entity.name == "no-refresh-create"

    def test_ret_dto_after_create(self, sync_session: Session):
        cu = _SyncTestCU(name="dto-create")
        dto = _SyncTestDAL.ret_dto_after_create(sync_session, cu)
        assert isinstance(dto, _SyncTestDTO)
        assert dto.name == "dto-create"

    def test_update_only_set(self, sync_session: Session):
        cu = _SyncTestCU(name="before-update", value=1)
        entity = _SyncTestDAL.create(sync_session, cu)

        update_cu = _SyncTestCU(name="after-update")
        updated = _SyncTestDAL.update_only_set_by_id(sync_session, entity.id, update_cu)
        assert updated is not None
        assert updated.name == "after-update"

    def test_update_only_set_nonexistent(self, sync_session: Session):
        cu = _SyncTestCU(name="ghost")
        result = _SyncTestDAL.update_only_set_by_id(sync_session, 999999, cu)
        assert result is None

    def test_ret_dto_after_update(self, sync_session: Session):
        cu = _SyncTestCU(name="before-dto-update")
        entity = _SyncTestDAL.create(sync_session, cu)
        update_cu = _SyncTestCU(name="after-dto-update")
        dto = _SyncTestDAL.ret_dto_after_update_by_id(sync_session, entity.id, update_cu)
        assert dto is not None
        assert dto.name == "after-dto-update"

    def test_ret_dto_after_update_nonexistent(self, sync_session: Session):
        cu = _SyncTestCU(name="ghost")
        result = _SyncTestDAL.ret_dto_after_update_by_id(sync_session, 999999, cu)
        assert result is None

    def test_update_full_by_id(self, sync_session: Session):
        cu = _SyncTestCU(name="full-before", value=10, status=1)
        entity = _SyncTestDAL.create(sync_session, cu)

        full_cu = _SyncTestCU(name="full-after", value=20, status=2)
        updated = _SyncTestDAL.update_full_by_id(sync_session, entity.id, full_cu)
        assert updated is not None
        assert updated.name == "full-after"
        assert updated.value == 20

    def test_update_full_nonexistent(self, sync_session: Session):
        cu = _SyncTestCU(name="ghost")
        result = _SyncTestDAL.update_full_by_id(sync_session, 999999, cu)
        assert result is None

    def test_update_partial_by_id(self, sync_session: Session):
        cu = _SyncTestCU(name="partial-before", value=10)
        entity = _SyncTestDAL.create(sync_session, cu)

        partial_cu = _SyncTestCU(name="partial-after")
        updated = _SyncTestDAL.update_partial_by_id(
            sync_session,
            entity.id,
            partial_cu,
            fields={_SyncTestTable.name},
        )
        assert updated is not None
        assert updated.name == "partial-after"
        assert updated.value == 10

    def test_update_partial_nonexistent(self, sync_session: Session):
        cu = _SyncTestCU(name="ghost")
        result = _SyncTestDAL.update_partial_by_id(sync_session, 999999, cu)
        assert result is None

    def test_update_partial_none_ignore(self, sync_session: Session):
        cu = _SyncTestCU(name="ignore-none", description="hello", value=5)
        entity = _SyncTestDAL.create(sync_session, cu)

        partial_cu = _SyncTestCU(name="ignore-none", description=None)
        updated = _SyncTestDAL.update_partial_by_id(
            sync_session,
            entity.id,
            partial_cu,
            none_policy="ignore",
        )
        assert updated is not None
        assert updated.description == "hello"

    def test_update_partial_none_allow(self, sync_session: Session):
        cu = _SyncTestCU(name="allow-none", description="hello")
        entity = _SyncTestDAL.create(sync_session, cu)

        partial_cu = _SyncTestCU(name="allow-none", description=None)
        updated = _SyncTestDAL.update_partial_by_id(
            sync_session,
            entity.id,
            partial_cu,
            none_policy="allow",
        )
        assert updated is not None
        assert updated.description is None

    def test_update_partial_none_forbid(self, sync_session: Session):
        cu = _SyncTestCU(name="forbid-none", description="hello")
        entity = _SyncTestDAL.create(sync_session, cu)

        partial_cu = _SyncTestCU(name="forbid-none", description=None)
        with pytest.raises(ValueError, match="字段不允许置空"):
            _SyncTestDAL.update_partial_by_id(
                sync_session,
                entity.id,
                partial_cu,
                none_policy="forbid",
            )

    def test_update_partial_none_policy_overrides(self, sync_session: Session):
        cu = _SyncTestCU(name="override", description="hello")
        entity = _SyncTestDAL.create(sync_session, cu)

        partial_cu = _SyncTestCU(name="override", description=None)
        updated = _SyncTestDAL.update_partial_by_id(
            sync_session,
            entity.id,
            partial_cu,
            none_policy="ignore",
            none_policy_overrides={_SyncTestTable.description: "allow"},
        )
        assert updated is not None
        assert updated.description is None

    def test_update_partial_strict(self, sync_session: Session):
        cu = _SyncTestCU(name="strict", value=1)
        entity = _SyncTestDAL.create(sync_session, cu)

        partial_cu = _SyncTestCU(name="strict", value=2, description="bad")
        with pytest.raises(ValueError, match="出现未允许更新的字段"):
            _SyncTestDAL.update_partial_by_id(
                sync_session,
                entity.id,
                partial_cu,
                fields={_SyncTestTable.name},
                strict=True,
            )

    def test_update_partial_column_field(self, sync_session: Session):
        cu = _SyncTestCU(name="col-field", value=1)
        entity = _SyncTestDAL.create(sync_session, cu)

        partial_cu = _SyncTestCU(name="col-field-updated")
        col = _SyncTestTable.__table__.c.name
        updated = _SyncTestDAL.update_partial_by_id(
            sync_session,
            entity.id,
            partial_cu,
            fields={col},
        )
        assert updated is not None
        assert updated.name == "col-field-updated"

    def test_update_partial_none_policy_overrides_column(self, sync_session: Session):
        cu = _SyncTestCU(name="col-override", description="hello")
        entity = _SyncTestDAL.create(sync_session, cu)

        partial_cu = _SyncTestCU(name="col-override", description=None)
        col = _SyncTestTable.__table__.c.description
        updated = _SyncTestDAL.update_partial_by_id(
            sync_session,
            entity.id,
            partial_cu,
            none_policy="ignore",
            none_policy_overrides={col: "allow"},
        )
        assert updated is not None
        assert updated.description is None

    def test_update_partial_fields_str_fallback(self, sync_session: Session):
        cu = _SyncTestCU(name="str-field", value=1)
        entity = _SyncTestDAL.create(sync_session, cu)

        partial_cu = _SyncTestCU(name="str-field-updated")
        updated = _SyncTestDAL.update_partial_by_id(
            sync_session,
            entity.id,
            partial_cu,
            fields={"name"},
        )
        assert updated is not None
        assert updated.name == "str-field-updated"

    def test_update_partial_none_overrides_str_fallback(self, sync_session: Session):
        cu = _SyncTestCU(name="str-override", description="hello")
        entity = _SyncTestDAL.create(sync_session, cu)

        partial_cu = _SyncTestCU(name="str-override", description=None)
        updated = _SyncTestDAL.update_partial_by_id(
            sync_session,
            entity.id,
            partial_cu,
            none_policy="ignore",
            none_policy_overrides={"description": "allow"},
        )
        assert updated is not None
        assert updated.description is None

    def test_delete_by_id(self, sync_session: Session):
        cu = _SyncTestCU(name="to-delete")
        entity = _SyncTestDAL.create(sync_session, cu)
        eid = entity.id
        assert _SyncTestDAL.delete_by_id(sync_session, eid) is True
        sync_session.expire_all()
        stmt = sa.select(_SyncTestTable).where(_SyncTestTable.id == eid)
        result = sync_session.execute(stmt)
        assert result.scalar_one_or_none() is None

    def test_delete_nonexistent(self, sync_session: Session):
        assert _SyncTestDAL.delete_by_id(sync_session, 999999) is False

    def test_get_all(self, sync_session: Session):
        _SyncTestDAL.create(sync_session, _SyncTestCU(name="all-1"))
        _SyncTestDAL.create(sync_session, _SyncTestCU(name="all-2"))
        dtos = _SyncTestDAL.get_all(sync_session, skip=0, limit=100)
        assert len(dtos) >= 2

    def test_count(self, sync_session: Session):
        _SyncTestDAL.create(sync_session, _SyncTestCU(name="count-1"))
        assert _SyncTestDAL.count(sync_session) >= 1

    def test_exists(self, sync_session: Session):
        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="exists"))
        assert _SyncTestDAL.exists(sync_session, entity.id) is True
        assert _SyncTestDAL.exists(sync_session, 999999) is False

    def test_ret_dto_after_get_by_id(self, sync_session: Session):
        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="dto-get"))
        dto = _SyncTestDAL.ret_dto_after_get_by_id(sync_session, entity.id)
        assert dto is not None
        assert dto.name == "dto-get"

    def test_ret_dto_after_get_by_id_no_refresh(self, sync_session: Session):
        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="no-refresh"))
        dto = _SyncTestDAL.ret_dto_after_get_by_id(sync_session, entity.id, need_refresh=False)
        assert dto is not None

    def test_ret_dto_after_get_by_id_nonexistent(self, sync_session: Session):
        dto = _SyncTestDAL.ret_dto_after_get_by_id(sync_session, 999999)
        assert dto is None


class TestSyncBatch:
    def test_batch_get_id__entity(self, sync_session: Session):
        e1 = _SyncTestDAL.create(sync_session, _SyncTestCU(name="b1"))
        e2 = _SyncTestDAL.create(sync_session, _SyncTestCU(name="b2"))
        result = _SyncTestDAL.batch_get_id__entity(sync_session, [e1.id, e2.id])
        assert e1.id in result
        assert e2.id in result

    def test_batch_get_id__entity_empty(self, sync_session: Session):
        result = _SyncTestDAL.batch_get_id__entity(sync_session, [])
        assert result == {}

    def test_batch_get_id__dto(self, sync_session: Session):
        e = _SyncTestDAL.create(sync_session, _SyncTestCU(name="batch-dto"))
        result = _SyncTestDAL.batch_get_id__dto(sync_session, [e.id])
        assert e.id in result
        assert isinstance(result[e.id], _SyncTestDTO)

    def test_batch_get_field__entity(self, sync_session: Session):
        _SyncTestDAL.create(sync_session, _SyncTestCU(name="field-batch"))
        result = _SyncTestDAL.batch_get_field__entity(
            sync_session,
            field_name="name",
            field_values=["field-batch"],
        )
        assert "field-batch" in result

    def test_batch_get_field__entity_empty(self, sync_session: Session):
        result = _SyncTestDAL.batch_get_field__entity(
            sync_session,
            field_name="name",
            field_values=[],
        )
        assert result == {}

    def test_batch_get_field__dto(self, sync_session: Session):
        _SyncTestDAL.create(sync_session, _SyncTestCU(name="field-dto"))
        result = _SyncTestDAL.batch_get_field__dto(
            sync_session,
            field_name="name",
            field_values=["field-dto"],
        )
        assert "field-dto" in result

    def test_batch_update_by_ids(self, sync_session: Session):
        e1 = _SyncTestDAL.create(sync_session, _SyncTestCU(name="bu1", value=0))
        e2 = _SyncTestDAL.create(sync_session, _SyncTestCU(name="bu2", value=0))
        affected = _SyncTestDAL.batch_update_by_ids(
            sync_session,
            entity_ids=[e1.id, e2.id],
            update_data={_SyncTestTable.value: 99},
            updater_id=1,
        )
        assert affected == 2

    def test_batch_update_by_ids_empty(self, sync_session: Session):
        affected = _SyncTestDAL.batch_update_by_ids(
            sync_session,
            entity_ids=[],
            update_data={_SyncTestTable.value: 1},
        )
        assert affected == 0

    def test_batch_update_by_conditions(self, sync_session: Session):
        e = _SyncTestDAL.create(sync_session, _SyncTestCU(name="cond-update", value=0))
        affected = _SyncTestDAL.batch_update_by_conditions(
            sync_session,
            whereclause=[_SyncTestTable.id == e.id],
            update_data={_SyncTestTable.value: 42},
        )
        assert affected == 1

    def test_batch_update_column_key(self, sync_session: Session):
        e = _SyncTestDAL.create(sync_session, _SyncTestCU(name="col-key", value=0))
        col = _SyncTestTable.__table__.c.value
        affected = _SyncTestDAL.batch_update_by_conditions(
            sync_session,
            whereclause=[_SyncTestTable.id == e.id],
            update_data={col: 88},
        )
        assert affected == 1

    def test_batch_update_str_key(self, sync_session: Session):
        e = _SyncTestDAL.create(sync_session, _SyncTestCU(name="str-key", value=0))
        affected = _SyncTestDAL.batch_update_by_conditions(
            sync_session,
            whereclause=[_SyncTestTable.id == e.id],
            update_data={"value": 77},
        )
        assert affected == 1

    def test_batch_update_invalid_key(self, sync_session: Session):
        e = _SyncTestDAL.create(sync_session, _SyncTestCU(name="bad-key", value=0))
        with pytest.raises(ValueError, match="不支持的更新条件类型"):
            _SyncTestDAL.batch_update_by_conditions(
                sync_session,
                whereclause=[_SyncTestTable.id == e.id],
                update_data={123: 77},
            )


class TestSyncIterators:
    def test_iter_records(self, sync_session: Session):
        _SyncTestDAL.create(sync_session, _SyncTestCU(name="iter-1"))
        _SyncTestDAL.create(sync_session, _SyncTestCU(name="iter-2"))
        records = list(_SyncTestDAL.iter_records(sync_session, batch_size=1))
        assert len(records) >= 2

    def test_iter_record_dtos(self, sync_session: Session):
        _SyncTestDAL.create(sync_session, _SyncTestCU(name="iter-dto"))
        dtos = list(_SyncTestDAL.iter_record_dtos(sync_session, batch_size=500))
        assert len(dtos) >= 1
        assert all(isinstance(d, _SyncTestDTO) for d in dtos)

    def test_iter_records_with_deleted(self, sync_session: Session):
        e = _SyncTestDAL.create(sync_session, _SyncTestCU(name="iter-del"))
        _SyncTestDAL.delete_by_id(sync_session, e.id)
        records = list(_SyncTestDAL.iter_records(sync_session, with_deleted=True, batch_size=500))
        ids = [r.id for r in records]
        assert e.id in ids

    def test_iter_records_with_where(self, sync_session: Session):
        _SyncTestDAL.create(sync_session, _SyncTestCU(name="where-iter", value=12345))
        records = list(
            _SyncTestDAL.iter_records(
                sync_session,
                where_clauses=[_SyncTestTable.value == 12345],
            )
        )
        assert all(r.value == 12345 for r in records)

    def test_iter_records_no_id_field(self, sync_session: Session):
        class _NoIdTable(SyncSqlATableBase):
            __tablename__ = "sync_no_id"
            key: Mapped[str] = mapped_column(sa.String(50), primary_key=True)

        SyncSqlATableBase.metadata.create_all(sync_session.get_bind(), checkfirst=True)

        with pytest.raises(ValueError, match="必须有 id 字段"):
            list(_SyncTestDAL._iter_records(sync_session, _NoIdTable))


class TestSyncOptimisticLock:
    def test_optimistic_lock_success(self, sync_session: Session):
        cu = _SyncVersionCU(name="opt-ok", value=10)
        entity = _SyncVersionDAL.create(sync_session, cu)

        update_cu = _SyncVersionCU(name="opt-ok-updated", value=20)
        updated = _SyncVersionDAL.update_only_set_with_optimistic_lock(
            sync_session,
            entity.id,
            update_cu,
            expected_version=0,
        )
        assert updated is not None
        assert updated.name == "opt-ok-updated"

    def test_optimistic_lock_conflict(self, sync_session: Session):
        cu = _SyncVersionCU(name="opt-conflict", value=10)
        entity = _SyncVersionDAL.create(sync_session, cu)

        update_cu = _SyncVersionCU(name="opt-conflict-updated")
        with pytest.raises(DBRetryableError, match="乐观锁更新失败"):
            _SyncVersionDAL.update_only_set_with_optimistic_lock(
                sync_session,
                entity.id,
                update_cu,
                expected_version=999,
            )

    def test_optimistic_lock_no_version_field(self, sync_session: Session):
        cu = _SyncTestCU(name="no-version")
        entity = _SyncTestDAL.create(sync_session, cu)

        with pytest.raises(AttributeError, match="不包含 version 字段"):
            _SyncTestDAL.update_only_set_with_optimistic_lock(
                sync_session,
                entity.id,
                cu,
                expected_version=0,
            )

    def test_optimistic_lock_empty_update(self, sync_session: Session):
        """Cover the 'if not update_data: return session.get(...)' branch (line 797-798)."""

        class _EmptyVersionCU(BaseCU["_SyncVersionTable"]):
            _Table: ClassVar[type[_SyncVersionTable]] = _SyncVersionTable
            name: str | None = None
            value: int | None = None

        cu = _SyncVersionCU(name="empty-opt")
        entity = _SyncVersionDAL.create(sync_session, cu)

        empty_cu = _EmptyVersionCU()
        result = _SyncVersionDAL.update_only_set_with_optimistic_lock(
            sync_session,
            entity.id,
            empty_cu,
            expected_version=0,
        )
        assert result is not None

    def test_optimistic_lock_with_refresh(self, sync_session: Session):
        cu = _SyncVersionCU(name="opt-refresh", value=10)
        entity = _SyncVersionDAL.create(sync_session, cu)

        update_cu = _SyncVersionCU(name="opt-refresh-updated")
        updated = _SyncVersionDAL.update_only_set_with_optimistic_lock(
            sync_session,
            entity.id,
            update_cu,
            expected_version=0,
            need_refresh=True,
        )
        assert updated is not None


class TestSyncReadonly:
    def test_readonly_session_prevents_write(self, sync_session: Session):
        sync_session.info[READONLY_SESSION_FLAG] = True
        cu = _SyncTestCU(name="readonly-fail")
        with pytest.raises(TypeError, match="只读"):
            _SyncTestDAL.create(sync_session, cu)

    def test_readonly_update(self, sync_session: Session):
        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="ro-update"))
        sync_session.info[READONLY_SESSION_FLAG] = True
        with pytest.raises(TypeError, match="只读"):
            _SyncTestDAL.update_only_set_by_id(sync_session, entity.id, _SyncTestCU(name="fail"))

    def test_readonly_update_full(self, sync_session: Session):
        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="ro-full"))
        sync_session.info[READONLY_SESSION_FLAG] = True
        with pytest.raises(TypeError, match="只读"):
            _SyncTestDAL.update_full_by_id(sync_session, entity.id, _SyncTestCU(name="fail"))

    def test_readonly_update_partial(self, sync_session: Session):
        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="ro-partial"))
        sync_session.info[READONLY_SESSION_FLAG] = True
        with pytest.raises(TypeError, match="只读"):
            _SyncTestDAL.update_partial_by_id(sync_session, entity.id, _SyncTestCU(name="fail"))

    def test_readonly_delete(self, sync_session: Session):
        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="ro-delete"))
        sync_session.info[READONLY_SESSION_FLAG] = True
        with pytest.raises(TypeError, match="只读"):
            _SyncTestDAL.delete_by_id(sync_session, entity.id)

    def test_readonly_batch_update(self, sync_session: Session):
        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="ro-batch"))
        sync_session.info[READONLY_SESSION_FLAG] = True
        with pytest.raises(TypeError, match="只读"):
            _SyncTestDAL.batch_update_by_conditions(
                sync_session,
                whereclause=[_SyncTestTable.id == entity.id],
                update_data={_SyncTestTable.value: 1},
            )

    def test_readonly_optimistic_lock(self, sync_session: Session):
        cu = _SyncVersionCU(name="ro-opt")
        entity = _SyncVersionDAL.create(sync_session, cu)
        sync_session.info[READONLY_SESSION_FLAG] = True
        with pytest.raises(TypeError, match="只读"):
            _SyncVersionDAL.update_only_set_with_optimistic_lock(
                sync_session,
                entity.id,
                cu,
                expected_version=0,
            )


class TestSyncReadOnlyDAL:
    def test_get_by_id(self, sync_session: Session):
        eid = _create_readonly_test_data(sync_session, "ro-get", 100)
        result = _SyncReadOnlyDAL.get_by_id(sync_session, eid)
        assert result is not None
        assert result.name == "ro-get"

    def test_dto_fields(self):
        fields = _SyncReadOnlyDAL._get_dto_fields(_SyncReadOnlyDTO)
        assert "name" in fields


class TestSyncRawSQL:
    def test_execute_sql(self, sync_session: Session):
        result = _SyncTestDAL.execute_sql(sync_session, "SELECT 1")
        assert result.scalar() == 1

    def test_execute_readonly_sql(self, sync_session: Session):
        result = _SyncTestDAL.execute_readonly_sql(sync_session, "SELECT 1")
        assert result.scalar() == 1

    def test_execute_readonly_sql_rejects_write(self, sync_session: Session):
        with pytest.raises(RuntimeError, match="只读DAL不允许执行写入操作"):
            _SyncTestDAL.execute_readonly_sql(sync_session, "INSERT INTO x VALUES (1)")

    def test_execute_readonly_text_clause(self, sync_session: Session):
        stmt = text("SELECT 1")
        result = _SyncTestDAL.execute_readonly_sql(sync_session, stmt)
        assert result.scalar() == 1

    def test_execute_sql_text_clause(self, sync_session: Session):
        stmt = text("SELECT 1")
        result = _SyncTestDAL.execute_sql(sync_session, stmt)
        assert result.scalar() == 1


class TestSyncRawSQLParamsBranches:
    def test_execute_readonly_sql_with_params(self, sync_session: Session):
        result = _SyncTestDAL.execute_readonly_sql(sync_session, "SELECT :val AS v", params={"val": 99})
        assert result.scalar() == 99

    def test_execute_sql_with_params(self, sync_session: Session):
        result = _SyncTestDAL.execute_sql(sync_session, "SELECT :val AS v", params={"val": 77})
        assert result.scalar() == 77


class TestSyncXDALOp:
    def test_xdal_execute_sql(self, sync_session: Session):
        result = SyncXDALOp.execute_sql(sync_session, "SELECT 1")
        assert result.scalar() == 1

    def test_xdal_execute_readonly_sql(self, sync_session: Session):
        result = SyncXDALOp.execute_readonly_sql(sync_session, "SELECT 1")
        assert result.scalar() == 1


class TestSyncRetry:
    def test_sync_with_retry_success(self):
        call_count = 0

        @sync_with_retry(RetryConfig(max_attempts=3, initial_delay=0.001, max_delay=0.01))
        def succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise DBRetryableError("conflict")
            return "ok"

        assert succeed() == "ok"
        assert call_count == 2

    def test_sync_with_retry_exhausted(self):
        @sync_with_retry(RetryConfig(max_attempts=2, initial_delay=0.001, max_delay=0.01))
        def always_fail():
            raise DBRetryableError("always conflict")

        with pytest.raises(DBRetryableError):
            always_fail()

    def test_sync_with_retry_on_conflict(self):
        conflicts = []

        def on_conflict(attempt, error):
            conflicts.append(attempt)

        @sync_with_retry(
            RetryConfig(max_attempts=3, initial_delay=0.001, max_delay=0.01),
            on_conflict=on_conflict,
        )
        def conflict_then_ok():
            if len(conflicts) < 1:
                raise DBRetryableError("conflict")
            return "ok"

        assert conflict_then_ok() == "ok"
        assert len(conflicts) >= 1

    def test_sync_with_retry_callback_failure(self):
        def bad_callback(attempt, error):
            raise RuntimeError("callback boom")

        call_count = 0

        @sync_with_retry(
            RetryConfig(max_attempts=3, initial_delay=0.001, max_delay=0.01),
            on_conflict=bad_callback,
        )
        def fail_once():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise DBRetryableError("conflict")
            return "ok"

        assert fail_once() == "ok"


class TestSyncSoftDelete:
    def test_soft_delete(self, sync_session: Session):
        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="soft-del"))
        eid = entity.id
        assert _SyncTestDAL.delete_by_id(sync_session, eid) is True
        sync_session.expire_all()

        stmt = sa.select(_SyncTestTable).where(_SyncTestTable.id == eid)
        result = sync_session.execute(stmt)
        assert result.scalar_one_or_none() is None

        stmt_with_del = sa.select(_SyncTestTable).where(_SyncTestTable.id == eid).execution_options(include_soft_deleted=True)
        result2 = sync_session.execute(stmt_with_del)
        deleted = result2.scalar_one_or_none()
        assert deleted is not None
        assert deleted.is_delete == 1


class TestSyncTempLockTimeout:
    def test_noop_when_none(self, sync_session: Session):
        with sync_temp_set_lock_wait_timeout(sync_session, None):
            pass


class TestSyncForUpdate:
    def test_get_by_id_for_update(self, sync_session: Session):
        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="for-update"))
        result = _SyncTestDAL.get_by_id_for_update(sync_session, entity.id)
        assert result is not None

    def test_batch_get_for_update(self, sync_session: Session):
        e1 = _SyncTestDAL.create(sync_session, _SyncTestCU(name="batch-fu1"))
        e2 = _SyncTestDAL.create(sync_session, _SyncTestCU(name="batch-fu2"))
        result = _SyncTestDAL.batch_get_for_update(sync_session, [e1.id, e2.id])
        assert len(result) == 2

    def test_batch_get_for_update_empty(self, sync_session: Session):
        assert _SyncTestDAL.batch_get_for_update(sync_session, []) == []

    def test_get_one_for_update(self, sync_session: Session):
        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="one-fu", value=54321))
        result = _SyncTestDAL.get_one_for_update(
            sync_session,
            where_clauses=[_SyncTestTable.value == 54321],
        )
        assert result is not None
        assert result.id == entity.id


class TestSyncLockTimeoutErrors:
    """Test pessimistic lock OperationalError → DBRetryableError branches."""

    def test_get_by_id_for_update_lock_timeout(self, sync_session: Session):
        from unittest.mock import patch

        from sqlalchemy.exc import OperationalError as SAOpError

        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="lock-timeout"))
        orig_execute = sync_session.execute

        def mock_execute(stmt, *args, **kwargs):
            orig = Exception("Lock wait timeout exceeded; try restarting transaction")
            raise SAOpError("", [], orig)

        with patch.object(sync_session, "execute", side_effect=mock_execute):
            with pytest.raises(DBRetryableError, match="悲观锁"):
                _SyncTestDAL.get_by_id_for_update(sync_session, entity.id)

    def test_get_by_id_for_update_other_operational_error(self, sync_session: Session):
        from unittest.mock import patch

        from sqlalchemy.exc import OperationalError as SAOpError

        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="other-error"))
        orig = Exception("Some other error")

        with patch.object(sync_session, "execute", side_effect=SAOpError("", [], orig)):
            with pytest.raises(SAOpError):
                _SyncTestDAL.get_by_id_for_update(sync_session, entity.id)

    def test_batch_get_for_update_lock_timeout(self, sync_session: Session):
        from unittest.mock import patch

        from sqlalchemy.exc import OperationalError as SAOpError

        e = _SyncTestDAL.create(sync_session, _SyncTestCU(name="batch-lock"))
        orig = Exception("Lock wait timeout exceeded")

        with patch.object(sync_session, "execute", side_effect=SAOpError("", [], orig)):
            with pytest.raises(DBRetryableError, match="悲观锁"):
                _SyncTestDAL.batch_get_for_update(sync_session, [e.id])

    def test_batch_get_for_update_other_error(self, sync_session: Session):
        from unittest.mock import patch

        from sqlalchemy.exc import OperationalError as SAOpError

        e = _SyncTestDAL.create(sync_session, _SyncTestCU(name="batch-other"))
        orig = Exception("Deadlock found")

        with patch.object(sync_session, "execute", side_effect=SAOpError("", [], orig)):
            with pytest.raises(SAOpError):
                _SyncTestDAL.batch_get_for_update(sync_session, [e.id])

    def test_get_one_for_update_lock_timeout(self, sync_session: Session):
        from unittest.mock import patch

        from sqlalchemy.exc import OperationalError as SAOpError

        _SyncTestDAL.create(sync_session, _SyncTestCU(name="one-lock", value=99999))
        orig = Exception("Lock wait timeout exceeded")

        with patch.object(sync_session, "execute", side_effect=SAOpError("", [], orig)):
            with pytest.raises(DBRetryableError, match="悲观锁"):
                _SyncTestDAL.get_one_for_update(
                    sync_session,
                    where_clauses=[_SyncTestTable.value == 99999],
                )

    def test_get_one_for_update_other_error(self, sync_session: Session):
        from unittest.mock import patch

        from sqlalchemy.exc import OperationalError as SAOpError

        orig = Exception("Connection lost")

        with patch.object(sync_session, "execute", side_effect=SAOpError("", [], orig)):
            with pytest.raises(SAOpError):
                _SyncTestDAL.get_one_for_update(
                    sync_session,
                    where_clauses=[_SyncTestTable.value == 99999],
                )

    def test_lock_timeout_with_1205_code(self, sync_session: Session):
        from unittest.mock import patch

        from sqlalchemy.exc import OperationalError as SAOpError

        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="code-1205"))
        orig = Exception("1205")

        with patch.object(sync_session, "execute", side_effect=SAOpError("", [], orig)):
            with pytest.raises(DBRetryableError, match="悲观锁"):
                _SyncTestDAL.get_by_id_for_update(sync_session, entity.id)


class TestSyncTempLockTimeoutReal:
    def test_with_timeout_value(self, sync_session: Session):
        with sync_temp_set_lock_wait_timeout(sync_session, 5):
            result = sync_session.execute(sa.text("SELECT 1"))
            assert result.scalar() == 1


class TestSyncOptimisticLockNoIdField:
    def test_optimistic_lock_no_id_field(self, sync_session: Session):
        class _NoIdCU(BaseCU["_SyncSimpleTable"]):
            _Table: ClassVar[type[_SyncSimpleTable]] = _SyncSimpleTable
            name: str

        class _NoIdDTO(BaseDTO[_NoIdCU]):
            _CU: ClassVar[type[_NoIdCU]] = _NoIdCU
            id: int
            name: str
            model_config = ConfigDict(from_attributes=True)

        class _NoIdVersionDAL(SyncWriteDAL[_SyncSimpleTable, _NoIdDTO, _NoIdCU]):
            _Table = _SyncSimpleTable
            _DTO = _NoIdDTO
            _CU = _NoIdCU

        cu = _NoIdCU(name="no-version-field")
        entity = _NoIdVersionDAL.create(sync_session, cu)
        with pytest.raises(AttributeError, match="不包含 version 字段"):
            _NoIdVersionDAL.update_only_set_with_optimistic_lock(
                sync_session,
                entity.id,
                cu,
                expected_version=0,
            )


class TestSyncUpdateEdgeCases:
    """Cover edge branches in update methods (hasattr checks, etc.)."""

    def test_update_full_skips_nonexistent_attr(self, sync_session: Session):
        """Cover branch: update_full sets only attributes that exist on the entity."""

        class _ExtraFieldCU(BaseCU["_SyncTestTable"]):
            _Table: ClassVar[type[_SyncTestTable]] = _SyncTestTable
            name: str
            nonexistent_column: str = "x"

        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="extra-field", value=1))
        cu = _ExtraFieldCU(name="extra-updated")
        updated = _SyncTestDAL.update_full_by_id(
            sync_session,
            entity.id,
            cu,
            strict_missing=False,
        )
        assert updated is not None
        assert updated.name == "extra-updated"

    def test_update_partial_skips_nonexistent_attr(self, sync_session: Session):
        """Cover hasattr(entity, key) false branch in update_partial_by_id."""

        class _ExtraPartialCU(BaseCU["_SyncTestTable"]):
            _Table: ClassVar[type[_SyncTestTable]] = _SyncTestTable
            name: str
            phantom_field: str = "y"

        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="partial-phantom", value=1))
        cu = _ExtraPartialCU(name="partial-phantom-updated", phantom_field="z")
        updated = _SyncTestDAL.update_partial_by_id(
            sync_session,
            entity.id,
            cu,
            none_policy="allow",
        )
        assert updated is not None
        assert updated.name == "partial-phantom-updated"

    def test_optimistic_lock_skips_nonexistent_attr(self, sync_session: Session):
        """Cover set_values filtering: keys not in _Table are excluded."""

        class _ExtraVersionCU(BaseCU["_SyncVersionTable"]):
            _Table: ClassVar[type[_SyncVersionTable]] = _SyncVersionTable
            name: str
            phantom_col: str = "x"

        entity = _SyncVersionDAL.create(sync_session, _SyncVersionCU(name="opt-phantom"))
        cu = _ExtraVersionCU(name="opt-phantom-updated", phantom_col="y")
        updated = _SyncVersionDAL.update_only_set_with_optimistic_lock(
            sync_session,
            entity.id,
            cu,
            expected_version=0,
        )
        assert updated is not None

    def test_update_only_set_skips_nonexistent_attr(self, sync_session: Session):
        """Cover hasattr check in update_only_set_by_id."""

        class _ExtraCU(BaseCU["_SyncTestTable"]):
            _Table: ClassVar[type[_SyncTestTable]] = _SyncTestTable
            name: str
            ghost_col: str = "g"

        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="set-ghost", value=1))
        cu = _ExtraCU(name="set-ghost-updated", ghost_col="h")
        updated = _SyncTestDAL.update_only_set_by_id(sync_session, entity.id, cu)
        assert updated is not None
        assert updated.name == "set-ghost-updated"


class TestSyncRetryEdge:
    def test_sync_with_retry_default_config(self):
        call_count = 0

        @sync_with_retry()
        def succeed():
            nonlocal call_count
            call_count += 1
            return "default"

        assert succeed() == "default"
        assert call_count == 1


class TestSyncRefreshBranches:
    """Cover need_refresh=True branches in update methods."""

    def test_update_full_with_refresh(self, sync_session: Session):
        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="ref-full", value=1))
        cu = _SyncTestCU(name="ref-full-updated", value=2)
        updated = _SyncTestDAL.update_full_by_id(
            sync_session,
            entity.id,
            cu,
            need_refresh=True,
        )
        assert updated is not None
        assert updated.name == "ref-full-updated"

    def test_update_partial_with_refresh(self, sync_session: Session):
        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="ref-partial", value=1))
        cu = _SyncTestCU(name="ref-partial-updated")
        updated = _SyncTestDAL.update_partial_by_id(
            sync_session,
            entity.id,
            cu,
            need_refresh=True,
        )
        assert updated is not None

    def test_update_full_strict_missing(self, sync_session: Session):
        """Test strict_missing branch via a CU whose model_dump omits a declared field."""

        class _StrictCU(BaseCU["_SyncTestTable"]):
            _Table: ClassVar[type[_SyncTestTable]] = _SyncTestTable
            name: str
            ghost_field: str = "x"

            def model_dump(self, **kwargs):
                d = super().model_dump(**kwargs)
                d.pop("ghost_field", None)
                return d

        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="strict-missing", value=1))
        cu = _StrictCU(name="strict-test")
        with pytest.raises(ValueError, match="缺少必须字段"):
            _SyncTestDAL.update_full_by_id(sync_session, entity.id, cu, strict_missing=True)

    def test_update_full_no_strict(self, sync_session: Session):
        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="no-strict", value=1))
        cu = _SyncTestCU(name="no-strict-updated")
        updated = _SyncTestDAL.update_full_by_id(
            sync_session,
            entity.id,
            cu,
            strict_missing=False,
        )
        assert updated is not None

    def test_update_partial_skipped_field(self, sync_session: Session):
        """When allowed_names is set and key not in allowed_names, the field is skipped."""
        entity = _SyncTestDAL.create(sync_session, _SyncTestCU(name="skip-field", value=1))
        cu = _SyncTestCU(name="skip-field-updated", value=99)
        updated = _SyncTestDAL.update_partial_by_id(
            sync_session,
            entity.id,
            cu,
            fields={_SyncTestTable.name},
        )
        assert updated is not None
        assert updated.name == "skip-field-updated"
        assert updated.value == 1

    def test_optimistic_lock_no_update_datetime(self, sync_session: Session):
        """Cover the branch where update_datetime is absent on the table."""

        class _NoDateTable(SyncSqlATableBase):
            __tablename__ = "sync_test_no_date"
            id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
            name: Mapped[str] = mapped_column(sa.String(50), nullable=False)
            version: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, default=0, server_default="0")

        SyncSqlATableBase.metadata.create_all(sync_session.get_bind(), checkfirst=True)

        class _NoDateCU(BaseCU["_NoDateTable"]):
            _Table: ClassVar[type[_NoDateTable]] = _NoDateTable
            name: str

        class _NoDateDTO(BaseDTO[_NoDateCU]):
            _CU: ClassVar[type[_NoDateCU]] = _NoDateCU
            id: int
            name: str
            version: int
            model_config = ConfigDict(from_attributes=True)

        class _NoDateDAL(SyncBaseDAL[_NoDateTable, _NoDateDTO, _NoDateCU]):
            _Table = _NoDateTable
            _DTO = _NoDateDTO
            _CU = _NoDateCU

        entity = _NoDateTable(name="no-date")
        sync_session.add(entity)
        sync_session.flush()

        cu = _NoDateCU(name="no-date-updated")
        updated = _NoDateDAL.update_only_set_with_optimistic_lock(
            sync_session,
            entity.id,
            cu,
            expected_version=0,
        )
        assert updated is not None

    def test_batch_update_no_update_datetime(self, sync_session: Session):
        """Cover the branch where update_datetime is absent in batch update."""

        class _NoDTTable(SyncSqlATableBase):
            __tablename__ = "sync_test_nodt"
            id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
            name: Mapped[str] = mapped_column(sa.String(50), nullable=False)
            value: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

        SyncSqlATableBase.metadata.create_all(sync_session.get_bind(), checkfirst=True)

        class _NoDTCU(BaseCU["_NoDTTable"]):
            _Table: ClassVar[type[_NoDTTable]] = _NoDTTable
            name: str
            value: int = 0

        class _NoDTDTO(BaseDTO[_NoDTCU]):
            _CU: ClassVar[type[_NoDTCU]] = _NoDTCU
            id: int
            name: str
            value: int
            model_config = ConfigDict(from_attributes=True)

        class _NoDTDAL(SyncBaseDAL[_NoDTTable, _NoDTDTO, _NoDTCU]):
            _Table = _NoDTTable
            _DTO = _NoDTDTO
            _CU = _NoDTCU

        entity = _NoDTTable(name="nodt", value=0)
        sync_session.add(entity)
        sync_session.flush()

        affected = _NoDTDAL.batch_update_by_conditions(
            sync_session,
            whereclause=[_NoDTTable.id == entity.id],
            update_data={_NoDTTable.value: 99},
        )
        assert affected == 1


class TestSyncFieldMixin:
    def test_data_json_bytes(self, sync_session: Session):
        class _DataModel(BaseModel):
            text: str = ""

        class _JsonTable(StdSyncBaseTable, FieldMixin.DataJsonBytes[_DataModel]):
            __tablename__ = "sync_test_json"
            data_json: Mapped[bytes] = mapped_column(sa.LargeBinary, nullable=True)

        _JsonTable._DATA_JSON = _DataModel
        SyncSqlATableBase.metadata.create_all(sync_session.get_bind(), checkfirst=True)

        obj = _JsonTable()
        obj.x_data_json = _DataModel(text="hello")
        assert obj.must_x_data_json.text == "hello"

        obj.x_data_json = None
        assert obj.x_data_json.text == ""

    def test_data_json_bytes_no_data_json(self):
        class _DataModel(BaseModel):
            text: str = ""

        class _NoDataJsonMixin(FieldMixin.DataJsonBytes[_DataModel]):
            pass

        obj = _NoDataJsonMixin()
        assert obj.x_data_json is None

    def test_data_json_bytes_str_raw(self, sync_session: Session):
        class _DataModel(BaseModel):
            text: str = ""

        class _StrJsonTable(StdSyncBaseTable, FieldMixin.DataJsonBytes[_DataModel]):
            __tablename__ = "sync_test_str_json"
            data_json: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)

        _StrJsonTable._DATA_JSON = _DataModel
        SyncSqlATableBase.metadata.create_all(sync_session.get_bind(), checkfirst=True)

        obj = _StrJsonTable()
        obj.data_json = '{"text": "from-str"}'
        result = obj.x_data_json
        assert result is not None
        assert result.text == "from-str"


# ========== lush-dal-protocol conformance suite ==========


from lush_dal_protocol.testing import SyncBaseDALConformanceTests as SyncDALConformanceTests

# ========== V2 Sync DAL tests ==========
from lush_sqlalchemyx.base.dal import (
    SQLALockOptions,
    SQLAOptimisticLockOptions,
    SQLAPartialUpdateOptions,
    SQLAUpdateOptions,
    SyncBaseDALV2,
)


class _SyncSimpleDALV2(SyncBaseDALV2[_SyncSimpleTable, _SyncSimpleDTO, _SyncSimpleCU]):
    _Table = _SyncSimpleTable
    _DTO = _SyncSimpleDTO
    _CU = _SyncSimpleCU


class _SyncTestDALV2(SyncBaseDALV2[_SyncTestTable, _SyncTestDTO, _SyncTestCU]):
    _Table = _SyncTestTable
    _DTO = _SyncTestDTO
    _CU = _SyncTestCU


class _SyncVersionDALV2(SyncBaseDALV2[_SyncVersionTable, _SyncVersionDTO, _SyncVersionCU]):
    _Table = _SyncVersionTable
    _DTO = _SyncVersionDTO
    _CU = _SyncVersionCU


class TestV2SyncDALBasicCRUD:
    """V2 Sync DAL 基础 CRUD — 验证不变的方法通过继承仍然工作."""

    def test_create_and_get_by_id(self, sync_session: Session):
        cu = _SyncSimpleCU(name="v2-sync")
        entity = _SyncSimpleDALV2.create(sync_session, cu)
        assert entity.id is not None
        found = _SyncSimpleDALV2.get_by_id(sync_session, entity.id)
        assert found is not None
        assert found.name == "v2-sync"

    def test_delete_by_id(self, sync_session: Session):
        entity = _SyncSimpleDALV2.create(sync_session, _SyncSimpleCU(name="v2-del"))
        assert _SyncSimpleDALV2.delete_by_id(sync_session, entity.id) is True
        assert _SyncSimpleDALV2.get_by_id(sync_session, entity.id) is None


class TestV2SyncDALLockMethods:
    """V2 Sync DAL lock 方法 — 使用 options 参数签名."""

    def test_get_by_id_for_update(self, sync_session: Session):
        entity = _SyncSimpleDALV2.create(sync_session, _SyncSimpleCU(name="v2-lock"))
        found = _SyncSimpleDALV2.get_by_id_for_update(sync_session, entity.id)
        assert found is not None

    def test_get_by_id_for_update_with_options(self, sync_session: Session):
        entity = _SyncSimpleDALV2.create(sync_session, _SyncSimpleCU(name="v2-lock-o"))
        found = _SyncSimpleDALV2.get_by_id_for_update(sync_session, entity.id, options=SQLALockOptions(timeout=5))
        assert found is not None

    def test_batch_get_for_update(self, sync_session: Session):
        e1 = _SyncSimpleDALV2.create(sync_session, _SyncSimpleCU(name="v2-b1"))
        e2 = _SyncSimpleDALV2.create(sync_session, _SyncSimpleCU(name="v2-b2"))
        result = _SyncSimpleDALV2.batch_get_for_update(sync_session, [e1.id, e2.id])
        assert len(result) == 2

    def test_batch_get_for_update_with_options(self, sync_session: Session):
        e = _SyncSimpleDALV2.create(sync_session, _SyncSimpleCU(name="v2-bo"))
        result = _SyncSimpleDALV2.batch_get_for_update(sync_session, [e.id], options=SQLALockOptions(timeout=3))
        assert len(result) == 1

    def test_batch_get_for_update_empty(self, sync_session: Session):
        assert _SyncSimpleDALV2.batch_get_for_update(sync_session, []) == []

    def test_get_one_for_update(self, sync_session: Session):
        e = _SyncSimpleDALV2.create(sync_session, _SyncSimpleCU(name="v2-one"))
        found = _SyncSimpleDALV2.get_one_for_update(sync_session, where_clauses=[_SyncSimpleTable.id == e.id])
        assert found is not None

    def test_get_one_for_update_with_options(self, sync_session: Session):
        e = _SyncSimpleDALV2.create(sync_session, _SyncSimpleCU(name="v2-one-o"))
        found = _SyncSimpleDALV2.get_one_for_update(
            sync_session,
            where_clauses=[_SyncSimpleTable.id == e.id],
            options=SQLALockOptions(timeout=2),
        )
        assert found is not None

    def test_optimistic_lock_with_options(self, sync_session: Session):
        entity = _SyncVersionDALV2.create(sync_session, _SyncVersionCU(name="v2-opt", value=1))
        opts = SQLAOptimisticLockOptions(version_field="version", need_refresh=True)
        updated = _SyncVersionDALV2.update_only_set_with_optimistic_lock(
            sync_session,
            entity.id,
            _SyncVersionCU(name="v2-opt2", value=2),
            expected_version=0,
            options=opts,
        )
        assert updated is not None

    def test_optimistic_lock_default_options(self, sync_session: Session):
        entity = _SyncVersionDALV2.create(sync_session, _SyncVersionCU(name="v2-opt-d", value=1))
        updated = _SyncVersionDALV2.update_only_set_with_optimistic_lock(
            sync_session,
            entity.id,
            _SyncVersionCU(name="v2-opt-d2", value=2),
            expected_version=0,
        )
        assert updated is not None


class TestV2SyncDALAdvancedWrite:
    """V2 Sync DAL 高级写操作 — 使用 options 参数签名."""

    def test_update_full_by_id(self, sync_session: Session):
        entity = _SyncTestDALV2.create(sync_session, _SyncTestCU(name="v2-full", value=1))
        updated = _SyncTestDALV2.update_full_by_id(
            sync_session,
            entity.id,
            _SyncTestCU(name="v2-full2", value=2),
        )
        assert updated is not None

    def test_update_full_by_id_with_options(self, sync_session: Session):
        entity = _SyncTestDALV2.create(sync_session, _SyncTestCU(name="v2-full-o", value=1))
        opts = SQLAUpdateOptions(need_refresh=True, strict_missing=False)
        updated = _SyncTestDALV2.update_full_by_id(
            sync_session,
            entity.id,
            _SyncTestCU(name="v2-full-o2", value=2),
            options=opts,
        )
        assert updated is not None

    def test_update_partial_by_id(self, sync_session: Session):
        entity = _SyncTestDALV2.create(sync_session, _SyncTestCU(name="v2-part", value=1))
        updated = _SyncTestDALV2.update_partial_by_id(
            sync_session,
            entity.id,
            _SyncTestCU(name="v2-part2"),
        )
        assert updated is not None

    def test_update_partial_by_id_with_options(self, sync_session: Session):
        entity = _SyncTestDALV2.create(sync_session, _SyncTestCU(name="v2-part-o", value=1))
        opts = SQLAPartialUpdateOptions(need_refresh=True, none_policy="allow")
        updated = _SyncTestDALV2.update_partial_by_id(
            sync_session,
            entity.id,
            _SyncTestCU(name="v2-part-o2"),
            options=opts,
        )
        assert updated is not None

    def test_batch_update_by_conditions(self, sync_session: Session):
        e = _SyncTestDALV2.create(sync_session, _SyncTestCU(name="v2-bc", value=10))
        cnt = _SyncTestDALV2.batch_update_by_conditions(
            sync_session,
            conditions=[_SyncTestTable.id == e.id],
            update_data={_SyncTestTable.value: 20},
        )
        assert cnt == 1

    def test_batch_update_by_ids(self, sync_session: Session):
        e = _SyncTestDALV2.create(sync_session, _SyncTestCU(name="v2-bi", value=10))
        cnt = _SyncTestDALV2.batch_update_by_ids(
            sync_session,
            entity_ids=[e.id],
            update_data={_SyncTestTable.value: 30},
        )
        assert cnt == 1

    def test_batch_update_by_ids_empty(self, sync_session: Session):
        cnt = _SyncTestDALV2.batch_update_by_ids(
            sync_session,
            entity_ids=[],
            update_data={_SyncTestTable.value: 30},
        )
        assert cnt == 0


class TestStdSyncDeprecationWarnings:
    """Std* 同步基类弃用警告测试."""

    def test_std_sync_base_table_warns(self):
        with pytest.warns(DeprecationWarning, match="StdSyncBaseTable"):

            class _DeprecatedSync(StdSyncBaseTable):
                __tablename__ = "deprecated_sync_warn"

    def test_std_sync_abstract_subclass_no_warn(self):
        import warnings as _w

        with _w.catch_warnings():
            _w.simplefilter("error", DeprecationWarning)

            class _AbstractSync(StdSyncBaseTable):
                __abstract__ = True

    def test_std_readonly_sync_warns(self):
        from lush_sqlalchemyx.base.dal._sync import StdReadOnlySyncBaseTable

        with pytest.warns(DeprecationWarning, match="StdReadOnlySyncBaseTable"):

            class _DeprecatedROSync(StdReadOnlySyncBaseTable):
                __tablename__ = "deprecated_ro_sync_warn"

    def test_std_readonly_sync_abstract_no_warn(self):
        import warnings as _w

        from lush_sqlalchemyx.base.dal._sync import StdReadOnlySyncBaseTable

        with _w.catch_warnings():
            _w.simplefilter("error", DeprecationWarning)

            class _AbstractROSync(StdReadOnlySyncBaseTable):
                __abstract__ = True


class TestSyncDALConformance(SyncDALConformanceTests):
    """继承 lush-dal-protocol 一致性套件, 验证 SyncBaseDAL 符合协议约定."""

    @pytest.fixture
    def dal_class(self):
        return _SyncSimpleDAL

    @pytest.fixture
    def session(self, sync_session: Session):
        return sync_session

    @pytest.fixture
    def sample_cu(self):
        return _SyncSimpleCU(name="conformance-test")


class TestSyncDALV2Conformance(SyncDALConformanceTests):
    """继承 lush-dal-protocol 一致性套件, 验证 SyncBaseDALV2 符合协议约定."""

    @pytest.fixture
    def dal_class(self):
        return _SyncSimpleDALV2

    @pytest.fixture
    def session(self, sync_session: Session):
        return sync_session

    @pytest.fixture
    def sample_cu(self):
        return _SyncSimpleCU(name="v2-conformance-test")
