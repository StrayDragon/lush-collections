"""Base 读操作协议 — 无 EntityT, 适用于 Core DAL / 非 ORM 场景.

与 ``AbstractSyncReadDAL`` / ``AbstractAsyncReadDAL`` 的区别:
- 无 ``EntityT`` 泛型参数, 所有读取方法直接返回 DTO
- 无 ``need_refresh`` 参数 (无 ORM session.refresh 语义)
- 无 ``batch_get_id__entity`` / ``iter_record_dtos`` (ORM 特有)
- 方法为实例方法而非 classmethod (支持实例状态)
- ``session`` 为可选 keyword arg, 默认使用 ``NO_SESSION`` (构造注入时自动填充)

注意: ``list_by`` / ``count_by`` 等带过滤条件的方法由具体实现自行定义,
协议只定义最通用的核心操作.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic

from pydantic import BaseModel
from typing_extensions import TypeVar as TypeVarExt

from ._types import NO_SESSION, NoSession, PrimaryKeyT, SessionT

DTOModelT = TypeVarExt("DTOModelT", bound=BaseModel, default=BaseModel)


class BaseSyncReadDAL(ABC, Generic[SessionT, DTOModelT, PrimaryKeyT]):
    """同步只读 DAL 协议 — 直接返回 DTO, 无 ORM 实体层.

    ``session`` 为 keyword-only 参数, 默认 ``NO_SESSION``.
    实现方可通过构造注入绑定 session, 调用方无需显式传入.
    """

    @abstractmethod
    def get_by_id(
        self,
        entity_id: PrimaryKeyT,
        *,
        session: SessionT | NoSession = NO_SESSION,
    ) -> DTOModelT | None:
        """按主键获取记录, 返回 DTO.

        Args:
            entity_id: 主键值.
            session: 数据库 session / 连接, 默认使用构造注入值.
        """


class BaseAsyncReadDAL(ABC, Generic[SessionT, DTOModelT, PrimaryKeyT]):
    """异步只读 DAL 协议 — 语义与 ``BaseSyncReadDAL`` 一致, 所有方法为 ``async def``."""

    @abstractmethod
    async def get_by_id(
        self,
        entity_id: PrimaryKeyT,
        *,
        session: SessionT | NoSession = NO_SESSION,
    ) -> DTOModelT | None:
        """按主键获取记录, 返回 DTO.

        Args:
            entity_id: 主键值.
            session: 数据库 session / 连接, 默认使用构造注入值.
        """
