"""Base 写操作协议 — 无 EntityT, 适用于 Core DAL / 非 ORM 场景.

与 ``AbstractSyncWriteDAL`` / ``AbstractAsyncWriteDAL`` 的区别:
- 无 ``EntityT`` 泛型参数, 写入方法直接返回 DTO 或受影响行数
- 无 ``need_refresh`` 参数 (无 ORM session.refresh 语义)
- 无 ``ret_dto_after_create`` / ``ret_dto_after_update_by_id`` (Entity→DTO 转换不存在)
- 方法为实例方法而非 classmethod (支持实例状态)
- ``session`` 为可选 keyword arg, 默认使用 ``NO_SESSION`` (构造注入时自动填充)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic

from pydantic import BaseModel
from typing_extensions import TypeVar as TypeVarExt

from ._types import NO_SESSION, NoSession, PrimaryKeyT, SessionT

CUModelT = TypeVarExt("CUModelT", bound=BaseModel, default=BaseModel)
DTOModelT = TypeVarExt("DTOModelT", bound=BaseModel, default=BaseModel)


class BaseSyncWriteDAL(ABC, Generic[SessionT, DTOModelT, CUModelT, PrimaryKeyT]):
    """同步写入 DAL 协议 — 写入操作直接返回 DTO 或行数.

    ``session`` 为 keyword-only 参数, 默认 ``NO_SESSION``.
    写入操作不自动 commit, 事务由调用方控制.
    """

    @abstractmethod
    def create(
        self,
        cu: CUModelT,
        *,
        session: SessionT | NoSession = NO_SESSION,
    ) -> DTOModelT:
        """创建记录, 返回创建后的 DTO.

        Args:
            cu: Create/Update 模型实例.
            session: 数据库 session / 连接, 默认使用构造注入值.
        """

    @abstractmethod
    def update_by_id(
        self,
        entity_id: PrimaryKeyT,
        cu: CUModelT,
        *,
        session: SessionT | NoSession = NO_SESSION,
    ) -> int:
        """按主键更新记录 (仅更新 CU 中已设置的字段), 返回受影响行数.

        Args:
            entity_id: 主键值.
            cu: Create/Update 模型实例.
            session: 数据库 session / 连接, 默认使用构造注入值.
        """

    @abstractmethod
    def delete_by_id(
        self,
        entity_id: PrimaryKeyT,
        *,
        session: SessionT | NoSession = NO_SESSION,
    ) -> bool:
        """按主键删除记录 (软删除或物理删除).

        Args:
            entity_id: 主键值.
            session: 数据库 session / 连接, 默认使用构造注入值.
        """


class BaseAsyncWriteDAL(ABC, Generic[SessionT, DTOModelT, CUModelT, PrimaryKeyT]):
    """异步写入 DAL 协议 — 语义与 ``BaseSyncWriteDAL`` 一致, 所有方法为 ``async def``."""

    @abstractmethod
    async def create(
        self,
        cu: CUModelT,
        *,
        session: SessionT | NoSession = NO_SESSION,
    ) -> DTOModelT:
        """创建记录, 返回创建后的 DTO.

        Args:
            cu: Create/Update 模型实例.
            session: 数据库 session / 连接, 默认使用构造注入值.
        """

    @abstractmethod
    async def update_by_id(
        self,
        entity_id: PrimaryKeyT,
        cu: CUModelT,
        *,
        session: SessionT | NoSession = NO_SESSION,
    ) -> int:
        """按主键更新记录, 返回受影响行数.

        Args:
            entity_id: 主键值.
            cu: Create/Update 模型实例.
            session: 数据库 session / 连接, 默认使用构造注入值.
        """

    @abstractmethod
    async def delete_by_id(
        self,
        entity_id: PrimaryKeyT,
        *,
        session: SessionT | NoSession = NO_SESSION,
    ) -> bool:
        """按主键删除记录.

        Args:
            entity_id: 主键值.
            session: 数据库 session / 连接, 默认使用构造注入值.
        """
