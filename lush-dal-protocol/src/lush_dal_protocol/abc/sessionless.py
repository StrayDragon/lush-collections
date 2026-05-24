"""无 Session 的 DAL ABC 层 — 适用于 Django ORM / Peewee / TortoiseORM 等无显式 session 的 ORM.

这些 ABC 与 session-based 版本语义一致, 仅去掉了 session 参数.
适合由框架自动管理数据库连接的 ORM.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterable, Iterator
from typing import Any, Generic

from lush_dal_protocol.abc._types import EntityT, PrimaryKeyT
from lush_dal_protocol.dto import CUModelT, DTOModelT
from lush_dal_protocol.params.extra import ExtraT

# ─── Sync ───────────────────────────────────────────────


class AbstractSyncSessionlessReadDAL(ABC, Generic[EntityT, DTOModelT, PrimaryKeyT, ExtraT]):
    """无 session 的同步只读 DAL 抽象基类."""

    @classmethod
    @abstractmethod
    def get_by_id(cls, entity_id: PrimaryKeyT, extra: ExtraT | None = None) -> EntityT | None:
        """根据主键 ID 获取单个 ORM 实体."""
        ...

    @classmethod
    @abstractmethod
    def get_all(cls, skip: int = 0, limit: int = 100, extra: ExtraT | None = None) -> list[DTOModelT]:
        """分页获取实体列表, 以 DTO 形式返回."""
        ...

    @classmethod
    @abstractmethod
    def count(cls, extra: ExtraT | None = None) -> int:
        """统计实体总数."""
        ...

    @classmethod
    @abstractmethod
    def exists(cls, entity_id: PrimaryKeyT, extra: ExtraT | None = None) -> bool:
        """判断指定 ID 的实体是否存在."""
        ...

    @classmethod
    @abstractmethod
    def ret_dto_after_get_by_id(cls, entity_id: PrimaryKeyT, need_refresh: bool = True, extra: ExtraT | None = None) -> DTOModelT | None:
        """根据主键 ID 获取实体并转为 DTO 返回."""
        ...

    @classmethod
    @abstractmethod
    def batch_get_id__entity(cls, entity_ids: Iterable[PrimaryKeyT], extra: ExtraT | None = None) -> dict[PrimaryKeyT, EntityT]:
        """批量获取实体, 返回 {id: entity} 字典."""
        ...

    @classmethod
    @abstractmethod
    def batch_get_id__dto(cls, entity_ids: Iterable[PrimaryKeyT], extra: ExtraT | None = None) -> dict[PrimaryKeyT, DTOModelT]:
        """批量获取实体, 返回 {id: DTO} 字典."""
        ...

    @classmethod
    @abstractmethod
    def iter_record_dtos(cls, extra: ExtraT | None = None, *, batch_size: int = 500) -> Iterator[DTOModelT]:
        """以迭代器方式逐条返回全部记录的 DTO."""
        ...


class AbstractSyncSessionlessWriteDAL(ABC, Generic[EntityT, DTOModelT, CUModelT, PrimaryKeyT, ExtraT]):
    """无 session 的同步写入 DAL 抽象基类."""

    @classmethod
    @abstractmethod
    def create(cls, cu: CUModelT, need_refresh: bool = True, extra: ExtraT | None = None) -> EntityT:
        """根据 CU 模型创建新实体."""
        ...

    @classmethod
    @abstractmethod
    def ret_dto_after_create(cls, cu: CUModelT, need_refresh: bool = True, extra: ExtraT | None = None) -> DTOModelT:
        """创建新实体并以 DTO 形式返回."""
        ...

    @classmethod
    @abstractmethod
    def update_only_set_by_id(
        cls, entity_id: PrimaryKeyT, cu: CUModelT, need_refresh: bool = False, extra: ExtraT | None = None
    ) -> EntityT | None:
        """仅更新 CU 中已设置 (非 unset) 的字段."""
        ...

    @classmethod
    @abstractmethod
    def ret_dto_after_update_by_id(
        cls, entity_id: PrimaryKeyT, cu: CUModelT, need_refresh: bool = True, extra: ExtraT | None = None
    ) -> DTOModelT | None:
        """更新实体并以 DTO 形式返回."""
        ...

    @classmethod
    @abstractmethod
    def delete_by_id(cls, entity_id: PrimaryKeyT, extra: ExtraT | None = None) -> bool:
        """根据主键 ID 删除实体."""
        ...


class AbstractSyncSessionlessBaseDAL(
    AbstractSyncSessionlessReadDAL[EntityT, DTOModelT, PrimaryKeyT, ExtraT],
    AbstractSyncSessionlessWriteDAL[EntityT, DTOModelT, CUModelT, PrimaryKeyT, ExtraT],
    ABC,
    Generic[EntityT, DTOModelT, CUModelT, PrimaryKeyT, ExtraT],
):
    """无 session 的同步完整 CRUD DAL 抽象基类 (Read + Write)."""


# ─── Async ──────────────────────────────────────────────


class AbstractAsyncSessionlessReadDAL(ABC, Generic[EntityT, DTOModelT, PrimaryKeyT, ExtraT]):
    """无 session 的异步只读 DAL 抽象基类."""

    @classmethod
    @abstractmethod
    async def get_by_id(cls, entity_id: PrimaryKeyT, extra: ExtraT | None = None) -> EntityT | None:
        """根据主键 ID 获取单个 ORM 实体."""
        ...

    @classmethod
    @abstractmethod
    async def get_all(cls, skip: int = 0, limit: int = 100, extra: ExtraT | None = None) -> list[DTOModelT]:
        """分页获取实体列表, 以 DTO 形式返回."""
        ...

    @classmethod
    @abstractmethod
    async def count(cls, extra: ExtraT | None = None) -> int:
        """统计实体总数."""
        ...

    @classmethod
    @abstractmethod
    async def exists(cls, entity_id: PrimaryKeyT, extra: ExtraT | None = None) -> bool:
        """判断指定 ID 的实体是否存在."""
        ...

    @classmethod
    @abstractmethod
    async def ret_dto_after_get_by_id(
        cls, entity_id: PrimaryKeyT, need_refresh: bool = True, extra: ExtraT | None = None
    ) -> DTOModelT | None:
        """根据主键 ID 获取实体并转为 DTO 返回."""
        ...

    @classmethod
    @abstractmethod
    async def batch_get_id__entity(cls, entity_ids: Iterable[PrimaryKeyT], extra: ExtraT | None = None) -> dict[PrimaryKeyT, EntityT]:
        """批量获取实体, 返回 {id: entity} 字典."""
        ...

    @classmethod
    @abstractmethod
    async def batch_get_id__dto(cls, entity_ids: Iterable[PrimaryKeyT], extra: ExtraT | None = None) -> dict[PrimaryKeyT, DTOModelT]:
        """批量获取实体, 返回 {id: DTO} 字典."""
        ...

    @classmethod
    @abstractmethod
    def iter_record_dtos(cls, extra: ExtraT | None = None, *, batch_size: int = 500) -> AsyncIterator[DTOModelT]:
        """以异步迭代器方式逐条返回全部记录的 DTO."""
        ...


class AbstractAsyncSessionlessWriteDAL(ABC, Generic[EntityT, DTOModelT, CUModelT, PrimaryKeyT, ExtraT]):
    """无 session 的异步写入 DAL 抽象基类."""

    @classmethod
    @abstractmethod
    async def create(cls, cu: CUModelT, need_refresh: bool = True, extra: ExtraT | None = None) -> EntityT:
        """根据 CU 模型创建新实体."""
        ...

    @classmethod
    @abstractmethod
    async def ret_dto_after_create(cls, cu: CUModelT, need_refresh: bool = True, extra: ExtraT | None = None) -> DTOModelT:
        """创建新实体并以 DTO 形式返回."""
        ...

    @classmethod
    @abstractmethod
    async def update_only_set_by_id(
        cls, entity_id: PrimaryKeyT, cu: CUModelT, need_refresh: bool = False, extra: ExtraT | None = None
    ) -> EntityT | None:
        """仅更新 CU 中已设置 (非 unset) 的字段."""
        ...

    @classmethod
    @abstractmethod
    async def ret_dto_after_update_by_id(
        cls, entity_id: PrimaryKeyT, cu: CUModelT, need_refresh: bool = True, extra: ExtraT | None = None
    ) -> DTOModelT | None:
        """更新实体并以 DTO 形式返回."""
        ...

    @classmethod
    @abstractmethod
    async def delete_by_id(cls, entity_id: PrimaryKeyT, extra: ExtraT | None = None) -> bool:
        """根据主键 ID 删除实体."""
        ...


class AbstractAsyncSessionlessBaseDAL(
    AbstractAsyncSessionlessReadDAL[EntityT, DTOModelT, PrimaryKeyT, ExtraT],
    AbstractAsyncSessionlessWriteDAL[EntityT, DTOModelT, CUModelT, PrimaryKeyT, ExtraT],
    ABC,
    Generic[EntityT, DTOModelT, CUModelT, PrimaryKeyT, ExtraT],
):
    """无 session 的异步完整 CRUD DAL 抽象基类 (Read + Write)."""


# ─── Lock (Sessionless) ────────────────────────────────


class AbstractSyncSessionlessLockDAL(ABC, Generic[EntityT, CUModelT, PrimaryKeyT, ExtraT]):
    """无 session 的同步锁操作 DAL 抽象基类."""

    @classmethod
    @abstractmethod
    def get_by_id_for_update(cls, entity_id: PrimaryKeyT, extra: ExtraT | None = None) -> EntityT | None:
        """以行锁方式获取实体."""
        ...

    @classmethod
    @abstractmethod
    def batch_get_for_update(cls, entity_ids: Iterable[PrimaryKeyT], extra: ExtraT | None = None) -> list[EntityT]:
        """批量以行锁方式获取实体."""
        ...

    @classmethod
    @abstractmethod
    def get_one_for_update(cls, extra: ExtraT | None = None, *, where_clauses: Any) -> EntityT | None:
        """根据条件以行锁方式获取单个实体."""
        ...

    @classmethod
    @abstractmethod
    def update_only_set_with_optimistic_lock(
        cls, entity_id: PrimaryKeyT, cu: CUModelT, extra: ExtraT | None = None, *, expected_version: int
    ) -> EntityT | None:
        """使用乐观锁更新实体, 版本不匹配时抛出 DBRetryableError."""
        ...


class AbstractAsyncSessionlessLockDAL(ABC, Generic[EntityT, CUModelT, PrimaryKeyT, ExtraT]):
    """无 session 的异步锁操作 DAL 抽象基类."""

    @classmethod
    @abstractmethod
    async def get_by_id_for_update(cls, entity_id: PrimaryKeyT, extra: ExtraT | None = None) -> EntityT | None:
        """以行锁方式获取实体."""
        ...

    @classmethod
    @abstractmethod
    async def batch_get_for_update(cls, entity_ids: Iterable[PrimaryKeyT], extra: ExtraT | None = None) -> list[EntityT]:
        """批量以行锁方式获取实体."""
        ...

    @classmethod
    @abstractmethod
    async def get_one_for_update(cls, extra: ExtraT | None = None, *, where_clauses: Any) -> EntityT | None:
        """根据条件以行锁方式获取单个实体."""
        ...

    @classmethod
    @abstractmethod
    async def update_only_set_with_optimistic_lock(
        cls, entity_id: PrimaryKeyT, cu: CUModelT, extra: ExtraT | None = None, *, expected_version: int
    ) -> EntityT | None:
        """使用乐观锁更新实体, 版本不匹配时抛出 DBRetryableError."""
        ...
