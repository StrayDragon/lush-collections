"""高级写操作 ABC 层."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic

from lush_dal_protocol.abc._types import EntityT, PrimaryKeyT, SessionT
from lush_dal_protocol.dto import CUModelT
from lush_dal_protocol.params.extra import ExtraT


class AbstractSyncAdvancedWriteDAL(ABC, Generic[SessionT, EntityT, CUModelT, PrimaryKeyT, ExtraT]):
    """同步高级写操作 DAL 抽象基类.

    通过 ExtraT 扩展 ORM 特有的更新选项.
    """

    @classmethod
    @abstractmethod
    def update_full_by_id(
        cls,
        session: SessionT,
        entity_id: PrimaryKeyT,
        cu: CUModelT,
        extra: ExtraT | None = None,
    ) -> EntityT | None:
        """全量更新实体 (所有字段)."""
        ...

    @classmethod
    @abstractmethod
    def update_partial_by_id(
        cls,
        session: SessionT,
        entity_id: PrimaryKeyT,
        cu: CUModelT,
        extra: ExtraT | None = None,
    ) -> EntityT | None:
        """部分更新实体 (按策略处理 None 值)."""
        ...

    @classmethod
    @abstractmethod
    def batch_update_by_conditions(
        cls,
        session: SessionT,
        extra: ExtraT | None = None,
        *,
        conditions: Any,
        update_data: Any,
        updater_id: PrimaryKeyT | None = None,
    ) -> int:
        """按条件批量更新, 返回受影响的行数."""
        ...

    @classmethod
    @abstractmethod
    def batch_update_by_ids(
        cls,
        session: SessionT,
        extra: ExtraT | None = None,
        *,
        entity_ids: set[PrimaryKeyT] | list[PrimaryKeyT],
        update_data: Any,
        updater_id: PrimaryKeyT | None = None,
    ) -> int:
        """按 ID 集合批量更新, 返回受影响的行数."""
        ...


class AbstractAsyncAdvancedWriteDAL(ABC, Generic[SessionT, EntityT, CUModelT, PrimaryKeyT, ExtraT]):
    """异步高级写操作 DAL 抽象基类.

    语义与 ``AbstractSyncAdvancedWriteDAL`` 一致, 所有方法为 ``async def``.
    """

    @classmethod
    @abstractmethod
    async def update_full_by_id(
        cls,
        session: SessionT,
        entity_id: PrimaryKeyT,
        cu: CUModelT,
        extra: ExtraT | None = None,
    ) -> EntityT | None:
        """全量更新实体 (所有字段)."""
        ...

    @classmethod
    @abstractmethod
    async def update_partial_by_id(
        cls,
        session: SessionT,
        entity_id: PrimaryKeyT,
        cu: CUModelT,
        extra: ExtraT | None = None,
    ) -> EntityT | None:
        """部分更新实体 (按策略处理 None 值)."""
        ...

    @classmethod
    @abstractmethod
    async def batch_update_by_conditions(
        cls,
        session: SessionT,
        extra: ExtraT | None = None,
        *,
        conditions: Any,
        update_data: Any,
        updater_id: PrimaryKeyT | None = None,
    ) -> int:
        """按条件批量更新, 返回受影响的行数."""
        ...

    @classmethod
    @abstractmethod
    async def batch_update_by_ids(
        cls,
        session: SessionT,
        extra: ExtraT | None = None,
        *,
        entity_ids: set[PrimaryKeyT] | list[PrimaryKeyT],
        update_data: Any,
        updater_id: PrimaryKeyT | None = None,
    ) -> int:
        """按 ID 集合批量更新, 返回受影响的行数."""
        ...
