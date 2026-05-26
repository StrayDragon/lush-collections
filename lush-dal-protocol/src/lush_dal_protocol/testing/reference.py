"""基于纯 Python 数据结构的 DAL 参考实现.

此模块提供一个完全基于内存字典的 DAL 实现, 用于:

1. 在 ``lush-dal-protocol`` 包内部验证 conformance 测试套件的正确性.
2. 作为下游 ORM 适配包的参考示例, 演示每个 ABC 方法的预期语义.

所有操作都在内存中进行, 不依赖任何外部数据库或 ORM.

用法示例::

    from lush_dal_protocol.testing.reference import (
        InMemorySyncDAL,
        InMemorySession,
        InMemoryCU,
    )

    session = InMemorySession()
    entity = InMemorySyncDAL.create(session, InMemoryCU(name="hello"))
    assert entity.name == "hello"
    assert InMemorySyncDAL.count(session) == 1
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any, ClassVar

from pydantic import ConfigDict

from lush_dal_protocol.abc.read import AbstractAsyncReadDAL, AbstractSyncReadDAL
from lush_dal_protocol.abc.write import AbstractAsyncWriteDAL, AbstractSyncWriteDAL
from lush_dal_protocol.dto import BaseCU, BaseDTO

# ─── Domain Models ─────────────────────────────────────────


class InMemoryEntity:
    """内存实体, 模拟数据库行.

    下游 ORM 适配包中对应的是具体 ORM 表模型 (如 SQLAlchemy DeclarativeBase).
    """

    def __init__(self, *, id: int = 0, name: str = "", version: int = 1) -> None:
        self.id = id
        self.name = name
        self.version = version


class InMemoryCU(BaseCU["InMemoryEntity"]):
    """内存 CU (Create/Update) 模型.

    下游适配包中对应的是业务 CU 模型, 继承 ``BaseCU`` 并绑定 ORM 表类.
    """

    _Table: ClassVar[type] = InMemoryEntity
    name: str = ""


class InMemoryDTO(BaseDTO[InMemoryCU]):
    """内存 DTO (Data Transfer Object) 模型.

    下游适配包中对应的是业务 DTO 模型, 继承 ``BaseDTO`` 并绑定 CU 类.
    """

    _CU: ClassVar[type] = InMemoryCU
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str = ""


# ─── Session ────────────────────────────────────────────────


@dataclass
class InMemorySession:
    """内存会话, 模拟数据库 session.

    下游适配包中对应的是 ORM 的 Session (如 ``sqlalchemy.orm.Session``).
    每个测试应创建独立实例以保证隔离性.
    """

    _store: dict[int, dict[str, Any]] = field(default_factory=dict)
    _next_id: int = 1

    def expire_all(self) -> None:
        """No-op: 内存数据始终是最新的, 无需过期刷新."""

    def _insert(self, data: dict[str, Any]) -> int:
        eid = self._next_id
        self._next_id += 1
        self._store[eid] = {**data, "id": eid}
        return eid

    def _get(self, eid: int) -> dict[str, Any] | None:
        row = self._store.get(eid)
        return dict(row) if row else None

    def _update(self, eid: int, data: dict[str, Any]) -> bool:
        if eid not in self._store:
            return False
        for k, v in data.items():
            if k != "id":
                self._store[eid][k] = v
        return True

    def _delete(self, eid: int) -> bool:
        return self._store.pop(eid, None) is not None

    def _all_rows(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._store.values()]

    def _count(self) -> int:
        return len(self._store)


# ─── Helpers ────────────────────────────────────────────────


def _row_to_entity(row: dict[str, Any]) -> InMemoryEntity:
    return InMemoryEntity(
        id=row["id"],
        name=row.get("name", ""),
        version=row.get("version", 1),
    )


def _row_to_dto(row: dict[str, Any]) -> InMemoryDTO:
    return InMemoryDTO(id=row["id"], name=row.get("name", ""))


def _cu_to_data(cu: InMemoryCU) -> dict[str, Any]:
    return cu.model_dump(exclude_unset=True, exclude={"id"})


def _must_get(session: InMemorySession, eid: int) -> dict[str, Any]:
    row = session._get(eid)
    if row is None:  # pragma: no cover
        raise AssertionError(f"row {eid} unexpectedly missing")
    return row


# ─── Sync DAL ───────────────────────────────────────────────


class InMemorySyncDAL(
    AbstractSyncReadDAL[InMemorySession, InMemoryEntity, InMemoryDTO, int],
    AbstractSyncWriteDAL[InMemorySession, InMemoryEntity, InMemoryDTO, InMemoryCU, int],
):
    """基于内存字典的同步 DAL 实现.

    实现了 Read + Write 全部 ABC 方法.
    作为 conformance 测试套件的参考验证对象.
    """

    # ── Read ──

    @classmethod
    def get_by_id(cls, session: InMemorySession, entity_id: int) -> InMemoryEntity | None:
        row = session._get(entity_id)
        return _row_to_entity(row) if row else None

    @classmethod
    def get_all(cls, session: InMemorySession, skip: int = 0, limit: int = 100) -> list[InMemoryDTO]:
        rows = session._all_rows()
        return [_row_to_dto(r) for r in rows[skip : skip + limit]]

    @classmethod
    def count(cls, session: InMemorySession) -> int:
        return session._count()

    @classmethod
    def exists(cls, session: InMemorySession, entity_id: int) -> bool:
        return session._get(entity_id) is not None

    @classmethod
    def ret_dto_after_get_by_id(cls, session: InMemorySession, entity_id: int, need_refresh: bool = True) -> InMemoryDTO | None:
        row = session._get(entity_id)
        return _row_to_dto(row) if row else None

    @classmethod
    def batch_get_id__entity(cls, session: InMemorySession, entity_ids: Iterable[int]) -> dict[int, InMemoryEntity]:
        result: dict[int, InMemoryEntity] = {}
        for eid in entity_ids:
            row = session._get(eid)
            if row:
                result[eid] = _row_to_entity(row)
        return result

    @classmethod
    def batch_get_id__dto(cls, session: InMemorySession, entity_ids: Iterable[int]) -> dict[int, InMemoryDTO]:
        result: dict[int, InMemoryDTO] = {}
        for eid in entity_ids:
            row = session._get(eid)
            if row:
                result[eid] = _row_to_dto(row)
        return result

    @classmethod
    def iter_record_dtos(cls, session: InMemorySession, *, batch_size: int = 500) -> Iterator[InMemoryDTO]:
        for row in session._all_rows():
            yield _row_to_dto(row)

    # ── Write ──

    @classmethod
    def create(cls, session: InMemorySession, cu: InMemoryCU, need_refresh: bool = True) -> InMemoryEntity:
        data = _cu_to_data(cu)
        data.setdefault("version", 1)
        eid = session._insert(data)
        return _row_to_entity(_must_get(session, eid))

    @classmethod
    def ret_dto_after_create(cls, session: InMemorySession, cu: InMemoryCU, need_refresh: bool = True) -> InMemoryDTO:
        entity = cls.create(session, cu, need_refresh)
        return _row_to_dto(_must_get(session, entity.id))

    @classmethod
    def update_only_set_by_id(
        cls,
        session: InMemorySession,
        entity_id: int,
        cu: InMemoryCU,
        need_refresh: bool = False,
    ) -> InMemoryEntity | None:
        if not session._update(entity_id, _cu_to_data(cu)):
            return None
        return _row_to_entity(_must_get(session, entity_id))

    @classmethod
    def ret_dto_after_update_by_id(
        cls,
        session: InMemorySession,
        entity_id: int,
        cu: InMemoryCU,
        need_refresh: bool = True,
    ) -> InMemoryDTO | None:
        entity = cls.update_only_set_by_id(session, entity_id, cu, need_refresh)
        if entity is None:
            return None
        return _row_to_dto(_must_get(session, entity.id))

    @classmethod
    def delete_by_id(cls, session: InMemorySession, entity_id: int) -> bool:
        return session._delete(entity_id)


# ─── Async DAL ──────────────────────────────────────────────


class InMemoryAsyncDAL(
    AbstractAsyncReadDAL[InMemorySession, InMemoryEntity, InMemoryDTO, int],
    AbstractAsyncWriteDAL[InMemorySession, InMemoryEntity, InMemoryDTO, InMemoryCU, int],
):
    """基于内存字典的异步 DAL 实现.

    所有方法委托给 ``InMemorySyncDAL`` 的同步实现, 无实际 I/O.
    用于验证异步 conformance 测试套件.
    """

    # ── Read ──

    @classmethod
    async def get_by_id(cls, session: InMemorySession, entity_id: int) -> InMemoryEntity | None:
        return InMemorySyncDAL.get_by_id(session, entity_id)

    @classmethod
    async def get_all(cls, session: InMemorySession, skip: int = 0, limit: int = 100) -> list[InMemoryDTO]:
        return InMemorySyncDAL.get_all(session, skip, limit)

    @classmethod
    async def count(cls, session: InMemorySession) -> int:
        return InMemorySyncDAL.count(session)

    @classmethod
    async def exists(cls, session: InMemorySession, entity_id: int) -> bool:
        return InMemorySyncDAL.exists(session, entity_id)

    @classmethod
    async def ret_dto_after_get_by_id(cls, session: InMemorySession, entity_id: int, need_refresh: bool = True) -> InMemoryDTO | None:
        return InMemorySyncDAL.ret_dto_after_get_by_id(session, entity_id, need_refresh)

    @classmethod
    async def batch_get_id__entity(cls, session: InMemorySession, entity_ids: Iterable[int]) -> dict[int, InMemoryEntity]:
        return InMemorySyncDAL.batch_get_id__entity(session, entity_ids)

    @classmethod
    async def batch_get_id__dto(cls, session: InMemorySession, entity_ids: Iterable[int]) -> dict[int, InMemoryDTO]:
        return InMemorySyncDAL.batch_get_id__dto(session, entity_ids)

    @classmethod
    def iter_record_dtos(cls, session: InMemorySession, *, batch_size: int = 500) -> AsyncIterator[InMemoryDTO]:
        async def _gen() -> AsyncIterator[InMemoryDTO]:
            for row in session._all_rows():
                yield _row_to_dto(row)

        return _gen()

    # ── Write ──

    @classmethod
    async def create(cls, session: InMemorySession, cu: InMemoryCU, need_refresh: bool = True) -> InMemoryEntity:
        return InMemorySyncDAL.create(session, cu, need_refresh)

    @classmethod
    async def ret_dto_after_create(cls, session: InMemorySession, cu: InMemoryCU, need_refresh: bool = True) -> InMemoryDTO:
        return InMemorySyncDAL.ret_dto_after_create(session, cu, need_refresh)

    @classmethod
    async def update_only_set_by_id(
        cls,
        session: InMemorySession,
        entity_id: int,
        cu: InMemoryCU,
        need_refresh: bool = False,
    ) -> InMemoryEntity | None:
        return InMemorySyncDAL.update_only_set_by_id(session, entity_id, cu, need_refresh)

    @classmethod
    async def ret_dto_after_update_by_id(
        cls,
        session: InMemorySession,
        entity_id: int,
        cu: InMemoryCU,
        need_refresh: bool = True,
    ) -> InMemoryDTO | None:
        return InMemorySyncDAL.ret_dto_after_update_by_id(session, entity_id, cu, need_refresh)

    @classmethod
    async def delete_by_id(cls, session: InMemorySession, entity_id: int) -> bool:
        return InMemorySyncDAL.delete_by_id(session, entity_id)
