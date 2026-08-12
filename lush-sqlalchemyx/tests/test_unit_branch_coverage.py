"""Targeted unit tests to reach 100% branch coverage.

These tests intentionally avoid real DB I/O (and SQLAlchemy greenlet bridges) by
using small fakes where possible, while still executing the real DAL logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import pytest
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

import lush_sqlalchemyx.base.dal as dal_mod
from lush_sqlalchemyx.base.dal import AsyncBaseDAL, BaseCU, BaseDTO

# 注册 DAL Session 事件钩子, 替代原先 import 时的 @listens_for 自动注册
dal_mod.setup_dal_hooks()


@dataclass
class _FakeExecuteResult:
    rowcount: int


class _FakeAsyncSession:
    def __init__(self, *, entities_by_id: dict[int, Any] | None = None) -> None:
        self.info: dict[str, Any] = {}
        self._entities_by_id = entities_by_id or {}

        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.refreshed: list[Any] = []
        self.executed: list[Any] = []
        self.flush_count = 0

    async def get(self, _table: Any, entity_id: int) -> Any:
        return self._entities_by_id.get(entity_id)

    def add(self, entity: Any) -> None:
        self.added.append(entity)

    async def delete(self, entity: Any) -> None:
        self.deleted.append(entity)

    async def flush(self) -> None:
        self.flush_count += 1

    async def refresh(self, entity: Any) -> None:
        self.refreshed.append(entity)

    async def execute(self, stmt: Any) -> _FakeExecuteResult:
        self.executed.append(stmt)
        return _FakeExecuteResult(rowcount=1)


class _UnitEntity:
    __slots__ = ("id", "name", "value")

    def __init__(self, *, name: str, value: int = 0) -> None:
        self.id = 1
        self.name = name
        self.value = value


class _UnitCU(BaseCU[_UnitEntity]):
    _Table: ClassVar[type[_UnitEntity]] = _UnitEntity

    name: str
    value: int = 0


class _UnitUpdateCU(BaseCU[_UnitEntity]):
    _Table: ClassVar[type[_UnitEntity]] = _UnitEntity

    name: str | None = None
    value: int | None = None
    unknown_field: str | None = None


class _UnitDTO(BaseDTO[_UnitCU]):
    _CU: ClassVar[type[_UnitCU]] = _UnitCU

    id: int
    name: str
    value: int

    model_config = ConfigDict(from_attributes=True)


class _UnitDAL(AsyncBaseDAL[_UnitEntity, _UnitDTO, _UnitCU]):
    _Table = _UnitEntity
    _DTO = _UnitDTO
    _CU = _UnitCU


def test_receive_before_flush_ignores_non_soft_delete_instance():
    """验证 before_flush 对非 SoftDeleteTableMixin 实例不做任何操作."""
    import lush_sqlalchemyx.base.dal._common as common_mod

    listener = getattr(common_mod, "_CommonModule__receive_before_flush", None) or getattr(common_mod, "__receive_before_flush")

    class _FakeSyncSession:
        def __init__(self) -> None:
            self.deleted = [object()]
            self.added: list[object] = []

        def add(self, obj: object) -> None:
            self.added.append(obj)

    listener(_FakeSyncSession(), flush_context=None, instances=None)


@pytest.mark.asyncio
async def test_ret_dto_after_get_by_id_need_refresh_false_skips_refresh():
    entity = _UnitEntity(name="n", value=1)
    session = _FakeAsyncSession(entities_by_id={1: entity})

    dto = await _UnitDAL.ret_dto_after_get_by_id(session, 1, need_refresh=False)  # type: ignore[arg-type]
    assert dto is not None
    assert dto.id == 1
    assert session.refreshed == []


@pytest.mark.asyncio
async def test_create_need_refresh_false_skips_refresh():
    session = _FakeAsyncSession()
    cu = _UnitCU(name="created", value=7)

    entity = await _UnitDAL.create(session, cu, need_refresh=False)  # type: ignore[arg-type]
    assert entity.name == "created"
    assert session.refreshed == []
    assert session.flush_count == 1
    assert session.added


@pytest.mark.asyncio
async def test_update_only_set_by_id_returns_none_when_missing():
    session = _FakeAsyncSession()
    cu = _UnitUpdateCU(name="x")
    result = await _UnitDAL.update_only_set_by_id(session, 999, cu)  # type: ignore[arg-type]
    assert result is None


@pytest.mark.asyncio
async def test_update_only_set_by_id_ignores_unknown_fields():
    entity = _UnitEntity(name="old", value=1)
    session = _FakeAsyncSession(entities_by_id={1: entity})

    cu = _UnitUpdateCU(name="new", unknown_field="ignored")
    result = await _UnitDAL.update_only_set_by_id(session, 1, cu)  # type: ignore[arg-type]

    assert result is entity
    assert entity.name == "new"
    assert not hasattr(entity, "unknown_field")


@pytest.mark.asyncio
async def test_update_only_set_by_id_default_allow_none():
    entity = _UnitEntity(name="old", value=1)
    session = _FakeAsyncSession(entities_by_id={1: entity})
    cu = _UnitUpdateCU(name=None, value=9)
    result = await _UnitDAL.update_only_set_by_id(session, 1, cu)  # type: ignore[arg-type]
    assert result is entity
    assert entity.name is None
    assert entity.value == 9


@pytest.mark.asyncio
async def test_update_only_set_by_id_ignore_none():
    entity = _UnitEntity(name="old", value=1)
    session = _FakeAsyncSession(entities_by_id={1: entity})
    cu = _UnitUpdateCU(name=None, value=3)
    result = await _UnitDAL.update_only_set_by_id(session, 1, cu, none_policy="ignore")  # type: ignore[arg-type]
    assert result is entity
    assert entity.name == "old"
    assert entity.value == 3


@pytest.mark.asyncio
async def test_update_only_set_by_id_forbid_none():
    entity = _UnitEntity(name="old", value=1)
    session = _FakeAsyncSession(entities_by_id={1: entity})
    cu = _UnitUpdateCU(name=None)
    with pytest.raises(ValueError, match="不允许置空"):
        await _UnitDAL.update_only_set_by_id(session, 1, cu, none_policy="forbid")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_update_full_by_id_returns_none_when_missing():
    session = _FakeAsyncSession()
    cu = _UnitCU(name="x", value=1)
    result = await _UnitDAL.update_full_by_id(session, 999, cu)  # type: ignore[arg-type]
    assert result is None


@pytest.mark.asyncio
async def test_update_full_by_id_strict_missing_false():
    entity = _UnitEntity(name="old", value=1)
    session = _FakeAsyncSession(entities_by_id={1: entity})

    cu = _UnitCU(name="new", value=2)
    result = await _UnitDAL.update_full_by_id(session, 1, cu, strict_missing=False)  # type: ignore[arg-type]
    assert result is entity
    assert entity.name == "new"


@pytest.mark.asyncio
async def test_update_full_by_id_ignores_unknown_fields():
    entity = _UnitEntity(name="old", value=1)
    session = _FakeAsyncSession(entities_by_id={1: entity})

    # update_full_by_id uses model_dump(exclude=update_exclude from cu_config), so even default None fields are included
    cu = _UnitUpdateCU(name="new", unknown_field="ignored")
    result = await _UnitDAL.update_full_by_id(session, 1, cu, strict_missing=False)  # type: ignore[arg-type]
    assert result is entity
    assert entity.name == "new"
    assert not hasattr(entity, "unknown_field")


@pytest.mark.asyncio
async def test_update_partial_by_id_ignores_unknown_fields():
    entity = _UnitEntity(name="old", value=1)
    session = _FakeAsyncSession(entities_by_id={1: entity})

    cu = _UnitUpdateCU(name="new", unknown_field="ignored")
    result = await _UnitDAL.update_partial_by_id(session, 1, cu)  # type: ignore[arg-type]
    assert result is entity
    assert entity.name == "new"
    assert not hasattr(entity, "unknown_field")


@pytest.mark.asyncio
async def test_delete_by_id_returns_false_when_missing():
    session = _FakeAsyncSession()
    ok = await _UnitDAL.delete_by_id(session, 999)  # type: ignore[arg-type]
    assert ok is False


def test_ensure_strict_fields_raises_when_not_allowed():
    with pytest.raises(ValueError, match="出现未允许更新的字段"):
        _UnitDAL._ensure_strict_fields(provided_keys={"a"}, allowed_names={"b"}, strict=True)


def test_ensure_strict_fields_all_allowed_no_error():
    _UnitDAL._ensure_strict_fields(provided_keys={"a"}, allowed_names={"a"}, strict=True)


class _Base(DeclarativeBase):
    pass


class _VersionedNoUpdateDatetime(_Base):
    __tablename__ = "unit_testing_versioned_no_update_datetime"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class _VersionedCU(BaseCU[_VersionedNoUpdateDatetime]):
    _Table: ClassVar[type[_VersionedNoUpdateDatetime]] = _VersionedNoUpdateDatetime

    name: str | None = None


class _VersionedDTO(BaseDTO[_VersionedCU]):
    _CU: ClassVar[type[_VersionedCU]] = _VersionedCU

    id: int
    name: str
    version: int

    model_config = ConfigDict(from_attributes=True)


class _VersionedDAL(AsyncBaseDAL[_VersionedNoUpdateDatetime, _VersionedDTO, _VersionedCU]):
    _Table = _VersionedNoUpdateDatetime
    _DTO = _VersionedDTO
    _CU = _VersionedCU


class _VersionedWithUpdateDatetime(_Base):
    __tablename__ = "unit_testing_versioned_with_update_datetime"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    update_datetime: Mapped[str | None] = mapped_column(String(32), nullable=True)


class _VersionedWithDtCU(BaseCU[_VersionedWithUpdateDatetime]):
    _Table: ClassVar[type[_VersionedWithUpdateDatetime]] = _VersionedWithUpdateDatetime
    name: str | None = None


class _VersionedWithDtDTO(BaseDTO[_VersionedWithDtCU]):
    _CU: ClassVar[type[_VersionedWithDtCU]] = _VersionedWithDtCU
    id: int
    name: str
    version: int
    model_config = ConfigDict(from_attributes=True)


class _VersionedWithDtDAL(AsyncBaseDAL[_VersionedWithUpdateDatetime, _VersionedWithDtDTO, _VersionedWithDtCU]):
    _Table = _VersionedWithUpdateDatetime
    _DTO = _VersionedWithDtDTO
    _CU = _VersionedWithDtCU


@pytest.mark.asyncio
async def test_update_only_set_with_optimistic_lock_table_without_audit_columns():
    entity = _VersionedNoUpdateDatetime(id=1, name="old", version=0)
    session = _FakeAsyncSession(entities_by_id={1: entity})

    _ = await _VersionedDAL.update_only_set_with_optimistic_lock(
        session,  # type: ignore[arg-type]
        1,
        _VersionedCU(name="new"),
        expected_version=0,
    )

    # Ensure the UPDATE statement was built/executed
    assert session.executed


@pytest.mark.asyncio
async def test_update_only_set_with_optimistic_lock_does_not_implicit_set_update_datetime():
    """表上有 update_datetime 列时乐观锁 UPDATE SQL 不含该列."""
    entity = _VersionedWithUpdateDatetime(id=1, name="old", version=0, update_datetime=None)
    session = _FakeAsyncSession(entities_by_id={1: entity})

    _ = await _VersionedWithDtDAL.update_only_set_with_optimistic_lock(
        session,  # type: ignore[arg-type]
        1,
        _VersionedWithDtCU(name="new"),
        expected_version=0,
    )
    assert session.executed
    assert entity.update_datetime is None
    from tests.oracle.pk_and_audit import oracle_update_sets_column

    assert not oracle_update_sets_column(session.executed[0], "update_datetime")


class _MsgData(BaseModel):
    text: str = ""


class _DataJsonBytesExample(dal_mod.FieldMixin.DataJsonBytes[_MsgData]):
    def __init__(self, data_json: bytes) -> None:
        self.data_json = data_json


class _SoftDeleteEntity(dal_mod.SoftDeleteTableMixin):
    """Minimal soft-delete entity for unit tests - NOT a real SQLAlchemy model."""

    def __init__(self, *, name: str, value: int = 0) -> None:
        self.id = 1
        self.name = name
        self.value = value


class _SoftDeleteCU(BaseCU["_SoftDeleteEntity"]):
    _Table: ClassVar[type[_SoftDeleteEntity]] = _SoftDeleteEntity

    name: str
    value: int = 0


class _SoftDeleteDTO(BaseDTO[_SoftDeleteCU]):
    _CU: ClassVar[type[_SoftDeleteCU]] = _SoftDeleteCU

    id: int
    name: str
    value: int

    model_config = ConfigDict(from_attributes=True)


class _SoftDeleteDAL(AsyncBaseDAL[_SoftDeleteEntity, _SoftDeleteDTO, _SoftDeleteCU]):
    _Table = _SoftDeleteEntity
    _DTO = _SoftDeleteDTO
    _CU = _SoftDeleteCU


@pytest.mark.asyncio
async def test_get_by_id_returns_none_for_soft_deleted_in_identity_map():
    entity = _SoftDeleteEntity(name="soft", value=1)
    entity.soft_delete()  # sets is_delete=1
    session = _FakeAsyncSession(entities_by_id={1: entity})

    result = await _SoftDeleteDAL.get_by_id(session, 1)  # type: ignore[arg-type]
    assert result is None


@pytest.mark.asyncio
async def test_exists_returns_false_for_soft_deleted_in_identity_map():
    entity = _SoftDeleteEntity(name="soft", value=1)
    entity.soft_delete()
    session = _FakeAsyncSession(entities_by_id={1: entity})

    ok = await _SoftDeleteDAL.exists(session, 1)  # type: ignore[arg-type]
    assert ok is False


@pytest.mark.asyncio
async def test_ret_dto_after_get_by_id_returns_none_for_soft_deleted():
    entity = _SoftDeleteEntity(name="soft", value=1)
    entity.soft_delete()
    session = _FakeAsyncSession(entities_by_id={1: entity})

    dto = await _SoftDeleteDAL.ret_dto_after_get_by_id(session, 1)  # type: ignore[arg-type]
    assert dto is None


def test_register_soft_delete_hooks_idempotent():
    """register_soft_delete_hooks is idempotent and does not raise when already registered."""
    dal_mod.register_soft_delete_hooks()
    assert dal_mod.is_soft_delete_hooks_registered()


def test_unregister_soft_delete_hooks_is_idempotent():
    """unregister_soft_delete_hooks works when hooks are active."""
    assert dal_mod.is_soft_delete_hooks_registered()
    dal_mod.unregister_soft_delete_hooks()
    assert not dal_mod.is_soft_delete_hooks_registered()
    # ensure idempotent
    dal_mod.unregister_soft_delete_hooks()
    assert not dal_mod.is_soft_delete_hooks_registered()
    # restore for other tests
    dal_mod.register_soft_delete_hooks()
    assert dal_mod.is_soft_delete_hooks_registered()


def test_setup_dal_hooks_registers_all():
    """setup_dal_hooks 注册所有钩子（幂等）。"""
    dal_mod.unregister_soft_delete_hooks()
    assert not dal_mod.is_soft_delete_hooks_registered()
    dal_mod.setup_dal_hooks()
    assert dal_mod.is_soft_delete_hooks_registered()


def test_setup_dal_hooks_registers_readonly_protection():
    """setup_dal_hooks 注册只读保护钩子分支."""
    from sqlalchemy import event
    from sqlalchemy.orm import Session as SyncSession

    import lush_sqlalchemyx.base.dal._common as common_mod

    readonly_fn = getattr(common_mod, "_CommonModule__prevent_readonly_write", None) or getattr(common_mod, "__prevent_readonly_write")
    if event.contains(SyncSession, "before_flush", readonly_fn):
        event.remove(SyncSession, "before_flush", readonly_fn)

    assert not event.contains(SyncSession, "before_flush", readonly_fn)
    dal_mod.setup_dal_hooks()
    assert event.contains(SyncSession, "before_flush", readonly_fn)
    _DataJsonBytesExample._DATA_JSON = _MsgData
    obj = _DataJsonBytesExample(b"{}")

    before = obj.data_json
    obj.x_data_json = {"not": "a model"}  # type: ignore[assignment]
    assert obj.data_json == before
