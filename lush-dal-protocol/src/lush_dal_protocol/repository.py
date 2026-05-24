"""Repository 高层声明式封装.

提供面向业务开发者的简化接口, 内部委托给 DAL 层.
隐藏 session 管理等 ORM 特有细节.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any, Generic

from lush_dal_protocol.abc._types import EntityT, PrimaryKeyT
from lush_dal_protocol.dto import CUModelT, DTOModelT
from lush_dal_protocol.params.pagination import CursorPagination, CursorResult, OffsetPagination, PageResult


class AbstractSyncRepository(ABC, Generic[EntityT, DTOModelT, CUModelT, PrimaryKeyT]):
    """同步 Repository ABC — 面向业务开发者的高层接口.

    下游 ORM 适配包继承后注入 session 管理方式.
    """

    # ─── 读操作 ───

    @classmethod
    @abstractmethod
    def get(cls, pk: PrimaryKeyT) -> EntityT | None:
        """根据主键获取实体."""
        ...

    @classmethod
    @abstractmethod
    def get_dto(cls, pk: PrimaryKeyT) -> DTOModelT | None:
        """根据主键获取 DTO."""
        ...

    @classmethod
    @abstractmethod
    def exists(cls, pk: PrimaryKeyT) -> bool:
        """判断实体是否存在."""
        ...

    @classmethod
    @abstractmethod
    def count(cls) -> int:
        """统计总数."""
        ...

    @classmethod
    @abstractmethod
    def list(cls, pagination: OffsetPagination | None = None) -> PageResult[DTOModelT]:
        """分页列表 (offset-based)."""
        ...

    @classmethod
    @abstractmethod
    def list_cursor(cls, pagination: CursorPagination | None = None) -> CursorResult[DTOModelT]:
        """分页列表 (cursor-based)."""
        ...

    # ─── 写操作 ───

    @classmethod
    @abstractmethod
    def create(cls, data: CUModelT) -> EntityT:
        """创建实体."""
        ...

    @classmethod
    @abstractmethod
    def update(cls, pk: PrimaryKeyT, data: CUModelT) -> EntityT | None:
        """更新实体 (仅设置非空字段)."""
        ...

    @classmethod
    @abstractmethod
    def delete(cls, pk: PrimaryKeyT) -> None:
        """删除实体."""
        ...

    # ─── 批量操作 ───

    @classmethod
    @abstractmethod
    def bulk_create(cls, items: Iterable[CUModelT]) -> list[EntityT]:
        """批量创建."""
        ...

    @classmethod
    @abstractmethod
    def bulk_update(cls, pks: Iterable[PrimaryKeyT], data: dict[str, Any]) -> int:
        """批量更新, 返回受影响行数."""
        ...

    @classmethod
    @abstractmethod
    def bulk_delete(cls, pks: Iterable[PrimaryKeyT]) -> int:
        """批量删除, 返回受影响行数."""
        ...


class AbstractAsyncRepository(ABC, Generic[EntityT, DTOModelT, CUModelT, PrimaryKeyT]):
    """异步 Repository ABC — 面向业务开发者的高层接口.

    语义与 ``AbstractSyncRepository`` 一致, 所有方法为 async.
    """

    # ─── 读操作 ───

    @classmethod
    @abstractmethod
    async def get(cls, pk: PrimaryKeyT) -> EntityT | None:
        """根据主键获取实体."""
        ...

    @classmethod
    @abstractmethod
    async def get_dto(cls, pk: PrimaryKeyT) -> DTOModelT | None:
        """根据主键获取 DTO."""
        ...

    @classmethod
    @abstractmethod
    async def exists(cls, pk: PrimaryKeyT) -> bool:
        """判断实体是否存在."""
        ...

    @classmethod
    @abstractmethod
    async def count(cls) -> int:
        """统计总数."""
        ...

    @classmethod
    @abstractmethod
    async def list(cls, pagination: OffsetPagination | None = None) -> PageResult[DTOModelT]:
        """分页列表 (offset-based)."""
        ...

    @classmethod
    @abstractmethod
    async def list_cursor(cls, pagination: CursorPagination | None = None) -> CursorResult[DTOModelT]:
        """分页列表 (cursor-based)."""
        ...

    # ─── 写操作 ───

    @classmethod
    @abstractmethod
    async def create(cls, data: CUModelT) -> EntityT:
        """创建实体."""
        ...

    @classmethod
    @abstractmethod
    async def update(cls, pk: PrimaryKeyT, data: CUModelT) -> EntityT | None:
        """更新实体 (仅设置非空字段)."""
        ...

    @classmethod
    @abstractmethod
    async def delete(cls, pk: PrimaryKeyT) -> None:
        """删除实体."""
        ...

    # ─── 批量操作 ───

    @classmethod
    @abstractmethod
    async def bulk_create(cls, items: Iterable[CUModelT]) -> list[EntityT]:
        """批量创建."""
        ...

    @classmethod
    @abstractmethod
    async def bulk_update(cls, pks: Iterable[PrimaryKeyT], data: dict[str, Any]) -> int:
        """批量更新, 返回受影响行数."""
        ...

    @classmethod
    @abstractmethod
    async def bulk_delete(cls, pks: Iterable[PrimaryKeyT]) -> int:
        """批量删除, 返回受影响行数."""
        ...
