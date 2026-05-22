"""写操作 ABC 层."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic

from lush_dal_protocol.abc._types import EntityT, SessionT
from lush_dal_protocol.dto import CUModelT, DTOModelT


class AbstractSyncWriteDAL(ABC, Generic[SessionT, EntityT, DTOModelT, CUModelT]):
    """同步写入 DAL 抽象基类.

    所有方法均为 classmethod, 接收显式 session 参数.
    写入操作执行 flush 而非 commit, 事务由调用方控制.
    """

    @classmethod
    @abstractmethod
    def create(cls, session: SessionT, cu: CUModelT, need_refresh: bool = True) -> EntityT:
        """根据 CU 模型创建新实体."""
        ...

    @classmethod
    @abstractmethod
    def ret_dto_after_create(cls, session: SessionT, cu: CUModelT, need_refresh: bool = True) -> DTOModelT:
        """创建新实体并以 DTO 形式返回."""
        ...

    @classmethod
    @abstractmethod
    def update_only_set_by_id(cls, session: SessionT, entity_id: int, cu: CUModelT, need_refresh: bool = False) -> EntityT | None:
        """仅更新 CU 中已设置 (非 unset) 的字段."""
        ...

    @classmethod
    @abstractmethod
    def ret_dto_after_update_by_id(
        cls,
        session: SessionT,
        entity_id: int,
        cu: CUModelT,
        need_refresh: bool = True,
    ) -> DTOModelT | None:
        """更新实体并以 DTO 形式返回."""
        ...

    @classmethod
    @abstractmethod
    def delete_by_id(cls, session: SessionT, entity_id: int) -> bool:
        """根据主键 ID 删除实体 (软删除或物理删除)."""
        ...


class AbstractAsyncWriteDAL(ABC, Generic[SessionT, EntityT, DTOModelT, CUModelT]):
    """异步写入 DAL 抽象基类.

    语义与 ``AbstractSyncWriteDAL`` 一致, 所有方法为 ``async def``.
    """

    @classmethod
    @abstractmethod
    async def create(cls, session: SessionT, cu: CUModelT, need_refresh: bool = True) -> EntityT:
        """根据 CU 模型创建新实体."""
        ...

    @classmethod
    @abstractmethod
    async def ret_dto_after_create(cls, session: SessionT, cu: CUModelT, need_refresh: bool = True) -> DTOModelT:
        """创建新实体并以 DTO 形式返回."""
        ...

    @classmethod
    @abstractmethod
    async def update_only_set_by_id(cls, session: SessionT, entity_id: int, cu: CUModelT, need_refresh: bool = False) -> EntityT | None:
        """仅更新 CU 中已设置 (非 unset) 的字段."""
        ...

    @classmethod
    @abstractmethod
    async def ret_dto_after_update_by_id(
        cls,
        session: SessionT,
        entity_id: int,
        cu: CUModelT,
        need_refresh: bool = True,
    ) -> DTOModelT | None:
        """更新实体并以 DTO 形式返回."""
        ...

    @classmethod
    @abstractmethod
    async def delete_by_id(cls, session: SessionT, entity_id: int) -> bool:
        """根据主键 ID 删除实体 (软删除或物理删除)."""
        ...
