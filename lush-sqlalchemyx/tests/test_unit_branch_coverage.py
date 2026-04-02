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
    class _FakeSyncSession:
        def __init__(self) -> None:
            self.deleted = [object()]
            self.added: list[object] = []

        def add(self, obj: object) -> None:
            self.added.append(obj)

    dal_mod.__receive_before_flush(_FakeSyncSession(), flush_context=None, instances=None)  # type: ignore[attr-defined]


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

    # update_full_by_id uses model_dump(exclude={"id"}), so even default None fields are included
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


@pytest.mark.asyncio
async def test_update_only_set_with_optimistic_lock_table_without_update_datetime_branch():
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


class _MsgData(BaseModel):
    text: str = ""


class _DataJsonBytesExample(dal_mod.FieldMixin.DataJsonBytes[_MsgData]):
    def __init__(self, data_json: bytes) -> None:
        self.data_json = data_json


def test_data_json_bytes_setter_non_basemodel_value_is_noop():
    _DataJsonBytesExample._DATA_JSON = _MsgData
    obj = _DataJsonBytesExample(b"{}")

    before = obj.data_json
    obj.x_data_json = {"not": "a model"}  # type: ignore[assignment]
    assert obj.data_json == before
