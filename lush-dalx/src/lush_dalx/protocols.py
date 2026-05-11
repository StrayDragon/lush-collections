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
    """同步只读 DAL 协议.

    定义了下游实现必须提供的只读数据访问方法.
    所有方法均为 classmethod, 接收显式 session 参数.
    """

    @classmethod
    def get_by_id(cls, session: SessionT, entity_id: int) -> EntityT | None:
        """根据主键 ID 获取单个 ORM 实体.

        Args:
            session: 数据库会话.
            entity_id: 实体主键 ID.

        Returns:
            找到则返回 ORM 实体实例, 否则返回 ``None``.

        行为约定:
            - 应支持软删除过滤 (如果实体混入了软删除标记).
            - 不应触发额外的 commit/flush.
        """
        ...

    @classmethod
    def get_all(cls, session: SessionT, skip: int = 0, limit: int = 100) -> list[DTOModelT]:
        """分页获取实体列表, 以 DTO 形式返回.

        Args:
            session: 数据库会话.
            skip: 跳过的记录数 (偏移量), 默认 0.
            limit: 最大返回数量, 默认 100.

        Returns:
            DTO 对象列表, 可能为空.

        行为约定:
            - skip=0, limit=100 为默认值.
            - 返回 DTO (而非 ORM 实体), 方便序列化.
            - 应按主键升序或插入顺序排列.
        """
        ...

    @classmethod
    def count(cls, session: SessionT) -> int:
        """统计实体总数.

        Args:
            session: 数据库会话.

        Returns:
            满足条件的记录数 (非负整数).

        行为约定:
            - 应排除软删除的记录.
            - 无记录时返回 0 而非 None.
        """
        ...

    @classmethod
    def exists(cls, session: SessionT, entity_id: int) -> bool:
        """判断指定 ID 的实体是否存在.

        Args:
            session: 数据库会话.
            entity_id: 实体主键 ID.

        Returns:
            存在返回 ``True``, 否则 ``False``.

        行为约定:
            - 应排除软删除的记录.
        """
        ...

    @classmethod
    def ret_dto_after_get_by_id(cls, session: SessionT, entity_id: int, need_refresh: bool = True) -> DTOModelT | None:
        """根据主键 ID 获取实体并转为 DTO 返回.

        Args:
            session: 数据库会话.
            entity_id: 实体主键 ID.
            need_refresh: 是否在返回前刷新实体 (从 DB 重新加载), 默认 True.

        Returns:
            找到则返回 DTO 对象, 否则返回 ``None``.

        行为约定:
            - need_refresh=True 时应确保返回的数据反映 DB 最新状态.
            - 转换为 DTO 时应使用 ``_DTO.model_validate(entity, from_attributes=True)``.
        """
        ...

    @classmethod
    def batch_get_id__entity(cls, session: SessionT, entity_ids: Iterable[int]) -> dict[int, EntityT]:
        """批量获取实体, 返回 {id: entity} 字典.

        Args:
            session: 数据库会话.
            entity_ids: 主键 ID 可迭代对象.

        Returns:
            存在的实体映射, key 为 ID, value 为 ORM 实体.
            不存在的 ID 不会出现在结果中.

        行为约定:
            - 应对 entity_ids 去重和过滤无效值 (None / 空字符串).
            - 使用 SQL IN 查询, 避免 N+1.
        """
        ...

    @classmethod
    def batch_get_id__dto(cls, session: SessionT, entity_ids: Iterable[int]) -> dict[int, DTOModelT]:
        """批量获取实体, 返回 {id: DTO} 字典.

        Args:
            session: 数据库会话.
            entity_ids: 主键 ID 可迭代对象.

        Returns:
            存在的实体映射, key 为 ID, value 为 DTO 对象.

        行为约定:
            - 语义同 ``batch_get_id__entity``, 但值为 DTO.
        """
        ...

    @classmethod
    def iter_record_dtos(cls, session: SessionT, *, batch_size: int = 500) -> Iterator[DTOModelT]:
        """以迭代器方式逐条返回全部记录的 DTO.

        Args:
            session: 数据库会话.
            batch_size: 每批从数据库拉取的记录数, 默认 500.

        Yields:
            DTOModelT: 逐条的 DTO 对象.

        行为约定:
            - 用于大数据量场景, 避免一次性加载全部记录到内存.
            - 内部应使用服务端游标 (yield_per / stream) 实现.
        """
        ...


@runtime_checkable
class SyncWriteDALProtocol(Protocol[SessionT, EntityT, DTOModelT, CUModelT]):
    """同步写入 DAL 协议.

    定义了下游实现必须提供的写入数据访问方法.
    所有方法均为 classmethod, 接收显式 session 参数.
    """

    @classmethod
    def create(cls, session: SessionT, cu: CUModelT, need_refresh: bool = True) -> EntityT:
        """根据 CU 模型创建新实体.

        Args:
            session: 数据库会话.
            cu: 创建/更新模型实例.
            need_refresh: 创建后是否刷新实体 (获取自增 ID 等 DB 端生成值), 默认 True.

        Returns:
            新创建的 ORM 实体实例.

        行为约定:
            - 调用 ``cu.to_orm_model()`` (或等效方法) 生成 ORM 实体.
            - 执行 ``session.add(entity)`` + ``session.flush()``.
            - need_refresh=True 时应额外调用 ``session.refresh(entity)``.
            - **不应** 自动 commit, 事务由调用方控制.
        """
        ...

    @classmethod
    def ret_dto_after_create(cls, session: SessionT, cu: CUModelT, need_refresh: bool = True) -> DTOModelT:
        """创建新实体并以 DTO 形式返回.

        Args:
            session: 数据库会话.
            cu: 创建/更新模型实例.
            need_refresh: 同 ``create`` 的 need_refresh.

        Returns:
            新创建实体对应的 DTO 对象.

        行为约定:
            - 语义等同于 ``cls.create(session, cu) → convert to DTO``.
        """
        ...

    @classmethod
    def update_only_set_by_id(cls, session: SessionT, entity_id: int, cu: CUModelT, need_refresh: bool = False) -> EntityT | None:
        """仅更新 CU 中已设置 (非 unset) 的字段.

        Args:
            session: 数据库会话.
            entity_id: 要更新的实体主键 ID.
            cu: 创建/更新模型, 仅 ``model_dump(exclude_unset=True)`` 中的字段会被更新.
            need_refresh: 更新后是否刷新, 默认 False.

        Returns:
            更新后的 ORM 实体, 若 ID 不存在则返回 ``None``.

        行为约定:
            - 使用 ``cu.model_dump(exclude_unset=True, exclude={\"id\"})`` 获取变更字段.
            - 仅 ``setattr`` 有效字段 (entity 上存在的属性).
            - 执行 ``session.flush()`` 而非 commit.
        """
        ...

    @classmethod
    def delete_by_id(cls, session: SessionT, entity_id: int) -> bool:
        """根据主键 ID 删除实体.

        Args:
            session: 数据库会话.
            entity_id: 要删除的实体主键 ID.

        Returns:
            成功删除返回 ``True``, ID 不存在返回 ``False``.

        行为约定:
            - 如果实体混入了 ``SoftDeleteTableMixin``, 应执行软删除 (标记 is_delete=1)
              而非物理删除.
            - 软删除通过 ``session.delete(entity)`` 触发 before_flush 事件实现.
            - 执行 ``session.flush()`` 而非 commit.
        """
        ...


@runtime_checkable
class SyncBaseDALProtocol(
    SyncReadDALProtocol[SessionT, EntityT, DTOModelT],
    SyncWriteDALProtocol[SessionT, EntityT, DTOModelT, CUModelT],
    Protocol[SessionT, EntityT, DTOModelT, CUModelT],
):
    """同步完整 DAL 协议 (读 + 写).

    组合了 ``SyncReadDALProtocol`` 和 ``SyncWriteDALProtocol`` 的全部方法.
    """

    ...


@runtime_checkable
class AsyncReadDALProtocol(Protocol[SessionT, EntityT, DTOModelT]):
    """异步只读 DAL 协议.

    语义与 ``SyncReadDALProtocol`` 完全一致, 所有方法为 ``async def``.
    详细行为约定请参见同步版对应方法的 docstring.
    """

    @classmethod
    async def get_by_id(cls, session: SessionT, entity_id: int) -> EntityT | None:
        """根据主键 ID 获取单个 ORM 实体 (异步版)."""
        ...

    @classmethod
    async def get_all(cls, session: SessionT, skip: int = 0, limit: int = 100) -> list[DTOModelT]:
        """分页获取实体列表, 以 DTO 形式返回 (异步版)."""
        ...

    @classmethod
    async def count(cls, session: SessionT) -> int:
        """统计实体总数 (异步版)."""
        ...

    @classmethod
    async def exists(cls, session: SessionT, entity_id: int) -> bool:
        """判断指定 ID 的实体是否存在 (异步版)."""
        ...

    @classmethod
    async def ret_dto_after_get_by_id(cls, session: SessionT, entity_id: int, need_refresh: bool = True) -> DTOModelT | None:
        """根据主键 ID 获取实体并转为 DTO 返回 (异步版)."""
        ...

    @classmethod
    async def batch_get_id__entity(cls, session: SessionT, entity_ids: Iterable[int]) -> dict[int, EntityT]:
        """批量获取实体, 返回 {id: entity} 字典 (异步版)."""
        ...

    @classmethod
    async def batch_get_id__dto(cls, session: SessionT, entity_ids: Iterable[int]) -> dict[int, DTOModelT]:
        """批量获取实体, 返回 {id: DTO} 字典 (异步版)."""
        ...

    @classmethod
    def iter_record_dtos(cls, session: SessionT, *, batch_size: int = 500) -> AsyncIterator[DTOModelT]:
        """以异步迭代器方式逐条返回全部记录的 DTO (异步版)."""
        ...


@runtime_checkable
class AsyncWriteDALProtocol(Protocol[SessionT, EntityT, DTOModelT, CUModelT]):
    """异步写入 DAL 协议.

    语义与 ``SyncWriteDALProtocol`` 完全一致, 所有方法为 ``async def``.
    详细行为约定请参见同步版对应方法的 docstring.
    """

    @classmethod
    async def create(cls, session: SessionT, cu: CUModelT, need_refresh: bool = True) -> EntityT:
        """根据 CU 模型创建新实体 (异步版)."""
        ...

    @classmethod
    async def ret_dto_after_create(cls, session: SessionT, cu: CUModelT, need_refresh: bool = True) -> DTOModelT:
        """创建新实体并以 DTO 形式返回 (异步版)."""
        ...

    @classmethod
    async def update_only_set_by_id(
        cls, session: SessionT, entity_id: int, cu: CUModelT, need_refresh: bool = False
    ) -> EntityT | None:
        """仅更新 CU 中已设置的字段 (异步版)."""
        ...

    @classmethod
    async def delete_by_id(cls, session: SessionT, entity_id: int) -> bool:
        """根据主键 ID 删除实体 (异步版)."""
        ...


@runtime_checkable
class AsyncBaseDALProtocol(
    AsyncReadDALProtocol[SessionT, EntityT, DTOModelT],
    AsyncWriteDALProtocol[SessionT, EntityT, DTOModelT, CUModelT],
    Protocol[SessionT, EntityT, DTOModelT, CUModelT],
):
    """异步完整 DAL 协议 (读 + 写).

    组合了 ``AsyncReadDALProtocol`` 和 ``AsyncWriteDALProtocol`` 的全部方法.
    """

    ...
