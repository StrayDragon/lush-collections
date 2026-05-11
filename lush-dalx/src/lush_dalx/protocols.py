"""DAL 操作协议 (Protocol) 定义.

定义了同步/异步两套 ReadDAL、WriteDAL、BaseDAL 的操作协议.
下游 ORM 适配包应实现这些协议以保持一致的用户接口.

注意: 这里的 Protocol 用 ``SessionT`` 和 ``EntityT`` 等泛型参数
屏蔽了具体 ORM 的会话和实体类型.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable, Iterator
from typing import Any, Protocol, TypeVar, runtime_checkable

from .dto import CUModelT, DTOModelT

SessionT = TypeVar("SessionT", contravariant=True)
EntityT = TypeVar("EntityT")


@runtime_checkable
class SyncReadDALProtocol(Protocol[SessionT, EntityT, DTOModelT]):
    """同步只读 DAL 协议."""

    @classmethod
    def get_by_id(cls, session: SessionT, entity_id: int) -> EntityT | None: ...

    @classmethod
    def get_all(cls, session: SessionT, skip: int = 0, limit: int = 100) -> list[DTOModelT]: ...

    @classmethod
    def count(cls, session: SessionT) -> int: ...

    @classmethod
    def exists(cls, session: SessionT, entity_id: int) -> bool: ...

    @classmethod
    def ret_dto_after_get_by_id(cls, session: SessionT, entity_id: int, need_refresh: bool = True) -> DTOModelT | None: ...

    @classmethod
    def batch_get_id__entity(cls, session: SessionT, entity_ids: Iterable[int]) -> dict[int, EntityT]: ...

    @classmethod
    def batch_get_id__dto(cls, session: SessionT, entity_ids: Iterable[int]) -> dict[int, DTOModelT]: ...

    @classmethod
    def iter_record_dtos(cls, session: SessionT, *, batch_size: int = 500) -> Iterator[DTOModelT]: ...


@runtime_checkable
class SyncWriteDALProtocol(Protocol[SessionT, EntityT, DTOModelT, CUModelT]):
    """同步写入 DAL 协议."""

    @classmethod
    def create(cls, session: SessionT, cu: CUModelT, need_refresh: bool = True) -> EntityT: ...

    @classmethod
    def ret_dto_after_create(cls, session: SessionT, cu: CUModelT, need_refresh: bool = True) -> DTOModelT: ...

    @classmethod
    def update_only_set_by_id(cls, session: SessionT, entity_id: int, cu: CUModelT, need_refresh: bool = False) -> EntityT | None: ...

    @classmethod
    def delete_by_id(cls, session: SessionT, entity_id: int) -> bool: ...


@runtime_checkable
class SyncBaseDALProtocol(
    SyncReadDALProtocol[SessionT, EntityT, DTOModelT],
    SyncWriteDALProtocol[SessionT, EntityT, DTOModelT, CUModelT],
    Protocol[SessionT, EntityT, DTOModelT, CUModelT],
):
    """同步完整 DAL 协议 (读 + 写)."""

    ...


@runtime_checkable
class AsyncReadDALProtocol(Protocol[SessionT, EntityT, DTOModelT]):
    """异步只读 DAL 协议."""

    @classmethod
    async def get_by_id(cls, session: SessionT, entity_id: int) -> EntityT | None: ...

    @classmethod
    async def get_all(cls, session: SessionT, skip: int = 0, limit: int = 100) -> list[DTOModelT]: ...

    @classmethod
    async def count(cls, session: SessionT) -> int: ...

    @classmethod
    async def exists(cls, session: SessionT, entity_id: int) -> bool: ...

    @classmethod
    async def ret_dto_after_get_by_id(cls, session: SessionT, entity_id: int, need_refresh: bool = True) -> DTOModelT | None: ...

    @classmethod
    async def batch_get_id__entity(cls, session: SessionT, entity_ids: Iterable[int]) -> dict[int, EntityT]: ...

    @classmethod
    async def batch_get_id__dto(cls, session: SessionT, entity_ids: Iterable[int]) -> dict[int, DTOModelT]: ...

    @classmethod
    def iter_record_dtos(cls, session: SessionT, *, batch_size: int = 500) -> AsyncIterator[DTOModelT]: ...


@runtime_checkable
class AsyncWriteDALProtocol(Protocol[SessionT, EntityT, DTOModelT, CUModelT]):
    """异步写入 DAL 协议."""

    @classmethod
    async def create(cls, session: SessionT, cu: CUModelT, need_refresh: bool = True) -> EntityT: ...

    @classmethod
    async def ret_dto_after_create(cls, session: SessionT, cu: CUModelT, need_refresh: bool = True) -> DTOModelT: ...

    @classmethod
    async def update_only_set_by_id(
        cls, session: SessionT, entity_id: int, cu: CUModelT, need_refresh: bool = False
    ) -> EntityT | None: ...

    @classmethod
    async def delete_by_id(cls, session: SessionT, entity_id: int) -> bool: ...


@runtime_checkable
class AsyncBaseDALProtocol(
    AsyncReadDALProtocol[SessionT, EntityT, DTOModelT],
    AsyncWriteDALProtocol[SessionT, EntityT, DTOModelT, CUModelT],
    Protocol[SessionT, EntityT, DTOModelT, CUModelT],
):
    """异步完整 DAL 协议 (读 + 写)."""

    ...
