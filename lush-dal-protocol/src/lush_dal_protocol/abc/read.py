"""读操作 ABC 层."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterable, Iterator
from typing import Generic

from lush_dal_protocol.abc._types import EntityT, PrimaryKeyT, SessionT
from lush_dal_protocol.dto import DTOModelT
from lush_dal_protocol.params.extra import ExtraT


class AbstractSyncReadDAL(ABC, Generic[SessionT, EntityT, DTOModelT, PrimaryKeyT, ExtraT]):
    """同步只读 DAL 抽象基类.

    所有方法均为 classmethod, 接收显式 session 参数.
    """

    @classmethod
    @abstractmethod
    def get_by_id(cls, session: SessionT, entity_id: PrimaryKeyT, extra: ExtraT | None = None) -> EntityT | None:
        """根据主键 ID 获取单个 ORM 实体."""
        ...

    @classmethod
    @abstractmethod
    def get_all(cls, session: SessionT, skip: int = 0, limit: int = 100, extra: ExtraT | None = None) -> list[DTOModelT]:
        """分页获取实体列表, 以 DTO 形式返回."""
        ...

    @classmethod
    @abstractmethod
    def count(cls, session: SessionT, extra: ExtraT | None = None) -> int:
        """统计实体总数 (排除软删除)."""
        ...

    @classmethod
    @abstractmethod
    def exists(cls, session: SessionT, entity_id: PrimaryKeyT, extra: ExtraT | None = None) -> bool:
        """判断指定 ID 的实体是否存在."""
        ...

    @classmethod
    @abstractmethod
    def ret_dto_after_get_by_id(
        cls, session: SessionT, entity_id: PrimaryKeyT, need_refresh: bool = True, extra: ExtraT | None = None
    ) -> DTOModelT | None:
        """根据主键 ID 获取实体并转为 DTO 返回."""
        ...

    @classmethod
    @abstractmethod
    def batch_get_id__entity(
        cls, session: SessionT, entity_ids: Iterable[PrimaryKeyT], extra: ExtraT | None = None
    ) -> dict[PrimaryKeyT, EntityT]:
        """批量获取实体, 返回 {id: entity} 字典."""
        ...

    @classmethod
    @abstractmethod
    def batch_get_id__dto(
        cls, session: SessionT, entity_ids: Iterable[PrimaryKeyT], extra: ExtraT | None = None
    ) -> dict[PrimaryKeyT, DTOModelT]:
        """批量获取实体, 返回 {id: DTO} 字典."""
        ...

    @classmethod
    @abstractmethod
    def iter_record_dtos(cls, session: SessionT, extra: ExtraT | None = None, *, batch_size: int = 500) -> Iterator[DTOModelT]:
        """以迭代器方式逐条返回全部记录的 DTO."""
        ...


class AbstractAsyncReadDAL(ABC, Generic[SessionT, EntityT, DTOModelT, PrimaryKeyT, ExtraT]):
    """异步只读 DAL 抽象基类.

    语义与 ``AbstractSyncReadDAL`` 一致, 所有方法为 ``async def``.
    """

    @classmethod
    @abstractmethod
    async def get_by_id(cls, session: SessionT, entity_id: PrimaryKeyT, extra: ExtraT | None = None) -> EntityT | None:
        """根据主键 ID 获取单个 ORM 实体."""
        ...

    @classmethod
    @abstractmethod
    async def get_all(cls, session: SessionT, skip: int = 0, limit: int = 100, extra: ExtraT | None = None) -> list[DTOModelT]:
        """分页获取实体列表, 以 DTO 形式返回."""
        ...

    @classmethod
    @abstractmethod
    async def count(cls, session: SessionT, extra: ExtraT | None = None) -> int:
        """统计实体总数 (排除软删除)."""
        ...

    @classmethod
    @abstractmethod
    async def exists(cls, session: SessionT, entity_id: PrimaryKeyT, extra: ExtraT | None = None) -> bool:
        """判断指定 ID 的实体是否存在."""
        ...

    @classmethod
    @abstractmethod
    async def ret_dto_after_get_by_id(
        cls, session: SessionT, entity_id: PrimaryKeyT, need_refresh: bool = True, extra: ExtraT | None = None
    ) -> DTOModelT | None:
        """根据主键 ID 获取实体并转为 DTO 返回."""
        ...

    @classmethod
    @abstractmethod
    async def batch_get_id__entity(
        cls, session: SessionT, entity_ids: Iterable[PrimaryKeyT], extra: ExtraT | None = None
    ) -> dict[PrimaryKeyT, EntityT]:
        """批量获取实体, 返回 {id: entity} 字典."""
        ...

    @classmethod
    @abstractmethod
    async def batch_get_id__dto(
        cls, session: SessionT, entity_ids: Iterable[PrimaryKeyT], extra: ExtraT | None = None
    ) -> dict[PrimaryKeyT, DTOModelT]:
        """批量获取实体, 返回 {id: DTO} 字典."""
        ...

    @classmethod
    @abstractmethod
    def iter_record_dtos(cls, session: SessionT, extra: ExtraT | None = None, *, batch_size: int = 500) -> AsyncIterator[DTOModelT]:
        """以异步迭代器方式逐条返回全部记录的 DTO."""
        ...
