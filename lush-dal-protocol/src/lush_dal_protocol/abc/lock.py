"""锁操作 ABC 层."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any, Generic

from lush_dal_protocol.abc._types import EntityT, PrimaryKeyT, SessionT
from lush_dal_protocol.dto import CUModelT
from lush_dal_protocol.params.extra import ExtraT


class AbstractSyncLockDAL(ABC, Generic[SessionT, EntityT, CUModelT, PrimaryKeyT, ExtraT]):
    """同步锁操作 DAL 抽象基类.

    通过 ExtraT 扩展 ORM 特有的锁选项 (如 timeout / nowait 等).
    """

    @classmethod
    @abstractmethod
    def get_by_id_for_update(
        cls,
        session: SessionT,
        entity_id: PrimaryKeyT,
        extra: ExtraT | None = None,
    ) -> EntityT | None:
        """以行锁方式获取实体."""
        ...

    @classmethod
    @abstractmethod
    def batch_get_for_update(
        cls,
        session: SessionT,
        entity_ids: Iterable[PrimaryKeyT],
        extra: ExtraT | None = None,
    ) -> list[EntityT]:
        """批量以行锁方式获取实体."""
        ...

    @classmethod
    @abstractmethod
    def get_one_for_update(
        cls,
        session: SessionT,
        extra: ExtraT | None = None,
        *,
        where_clauses: Any,
    ) -> EntityT | None:
        """根据条件以行锁方式获取单个实体."""
        ...

    @classmethod
    @abstractmethod
    def update_only_set_with_optimistic_lock(
        cls,
        session: SessionT,
        entity_id: PrimaryKeyT,
        cu: CUModelT,
        extra: ExtraT | None = None,
        *,
        expected_version: int,
    ) -> EntityT | None:
        """使用乐观锁更新实体, 版本不匹配时抛出 DBRetryableError."""
        ...


class AbstractAsyncLockDAL(ABC, Generic[SessionT, EntityT, CUModelT, PrimaryKeyT, ExtraT]):
    """异步锁操作 DAL 抽象基类.

    语义与 ``AbstractSyncLockDAL`` 一致, 所有方法为 ``async def``.
    """

    @classmethod
    @abstractmethod
    async def get_by_id_for_update(
        cls,
        session: SessionT,
        entity_id: PrimaryKeyT,
        extra: ExtraT | None = None,
    ) -> EntityT | None:
        """以行锁方式获取实体."""
        ...

    @classmethod
    @abstractmethod
    async def batch_get_for_update(
        cls,
        session: SessionT,
        entity_ids: Iterable[PrimaryKeyT],
        extra: ExtraT | None = None,
    ) -> list[EntityT]:
        """批量以行锁方式获取实体."""
        ...

    @classmethod
    @abstractmethod
    async def get_one_for_update(
        cls,
        session: SessionT,
        extra: ExtraT | None = None,
        *,
        where_clauses: Any,
    ) -> EntityT | None:
        """根据条件以行锁方式获取单个实体."""
        ...

    @classmethod
    @abstractmethod
    async def update_only_set_with_optimistic_lock(
        cls,
        session: SessionT,
        entity_id: PrimaryKeyT,
        cu: CUModelT,
        extra: ExtraT | None = None,
        *,
        expected_version: int,
    ) -> EntityT | None:
        """使用乐观锁更新实体, 版本不匹配时抛出 DBRetryableError."""
        ...
