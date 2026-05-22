"""高级写操作 ABC 层."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from lush_dal_protocol.abc._types import EntityT, SessionT
from lush_dal_protocol.dto import CUModelT
from lush_dal_protocol.params.update import PartialUpdateOptions, UpdateOptions

UpdateOptionsT = TypeVar("UpdateOptionsT", bound=UpdateOptions)
PartialUpdateOptionsT = TypeVar("PartialUpdateOptionsT", bound=PartialUpdateOptions)


class AbstractSyncAdvancedWriteDAL(ABC, Generic[SessionT, EntityT, CUModelT, UpdateOptionsT, PartialUpdateOptionsT]):
    """同步高级写操作 DAL 抽象基类.

    通过泛型参数 UpdateOptionsT / PartialUpdateOptionsT 实现 ORM 特定选项扩展.
    """

    @classmethod
    @abstractmethod
    def update_full_by_id(
        cls,
        session: SessionT,
        entity_id: int,
        cu: CUModelT,
        *,
        options: UpdateOptionsT | None = None,
    ) -> EntityT | None:
        """全量更新实体 (所有字段)."""
        ...

    @classmethod
    @abstractmethod
    def update_partial_by_id(
        cls,
        session: SessionT,
        entity_id: int,
        cu: CUModelT,
        *,
        options: PartialUpdateOptionsT | None = None,
    ) -> EntityT | None:
        """部分更新实体 (按策略处理 None 值)."""
        ...

    @classmethod
    @abstractmethod
    def batch_update_by_conditions(
        cls,
        session: SessionT,
        *,
        conditions: Any,
        update_data: Any,
        updater_id: int | None = None,
    ) -> int:
        """按条件批量更新, 返回受影响的行数."""
        ...

    @classmethod
    @abstractmethod
    def batch_update_by_ids(
        cls,
        session: SessionT,
        *,
        entity_ids: set[int] | list[int],
        update_data: Any,
        updater_id: int | None = None,
    ) -> int:
        """按 ID 集合批量更新, 返回受影响的行数."""
        ...


class AbstractAsyncAdvancedWriteDAL(ABC, Generic[SessionT, EntityT, CUModelT, UpdateOptionsT, PartialUpdateOptionsT]):
    """异步高级写操作 DAL 抽象基类.

    语义与 ``AbstractSyncAdvancedWriteDAL`` 一致, 所有方法为 ``async def``.
    """

    @classmethod
    @abstractmethod
    async def update_full_by_id(
        cls,
        session: SessionT,
        entity_id: int,
        cu: CUModelT,
        *,
        options: UpdateOptionsT | None = None,
    ) -> EntityT | None:
        """全量更新实体 (所有字段)."""
        ...

    @classmethod
    @abstractmethod
    async def update_partial_by_id(
        cls,
        session: SessionT,
        entity_id: int,
        cu: CUModelT,
        *,
        options: PartialUpdateOptionsT | None = None,
    ) -> EntityT | None:
        """部分更新实体 (按策略处理 None 值)."""
        ...

    @classmethod
    @abstractmethod
    async def batch_update_by_conditions(
        cls,
        session: SessionT,
        *,
        conditions: Any,
        update_data: Any,
        updater_id: int | None = None,
    ) -> int:
        """按条件批量更新, 返回受影响的行数."""
        ...

    @classmethod
    @abstractmethod
    async def batch_update_by_ids(
        cls,
        session: SessionT,
        *,
        entity_ids: set[int] | list[int],
        update_data: Any,
        updater_id: int | None = None,
    ) -> int:
        """按 ID 集合批量更新, 返回受影响的行数."""
        ...
