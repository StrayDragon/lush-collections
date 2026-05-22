"""V2 异步 DAL — 继承 lush-dal-protocol ABC, 使用统一 extra 参数.

V2 类继承 V1 实现 + ABC 接口, 仅覆写签名变更的方法.
不变的方法 (get_by_id, create, count 等) 直接继承自 V1 而不需要覆写.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Generic

from lush_dal_protocol.abc import (
    AbstractAsyncAdvancedWriteDAL,
    AbstractAsyncBatchFieldDAL,
    AbstractAsyncLockDAL,
    AbstractAsyncRawSQLDAL,
    AbstractAsyncReadDAL,
    AbstractAsyncWriteDAL,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from ._async import AsyncReadDAL, AsyncSQLATableT, AsyncWriteDAL
from ._common import CUModelT, DTOModelT, filtered_in_sql_values
from ._params import SQLAExtra


class AsyncReadDALV2(  # pyright: ignore[reportIncompatibleMethodOverride]
    AsyncReadDAL[AsyncSQLATableT, DTOModelT],
    AbstractAsyncReadDAL[AsyncSession, AsyncSQLATableT, DTOModelT, SQLAExtra],
    AbstractAsyncBatchFieldDAL[AsyncSession, AsyncSQLATableT, DTOModelT, SQLAExtra],
    Generic[AsyncSQLATableT, DTOModelT],
):
    """V2 异步只读 DAL — ABC 合规接口.

    与 V1 共享全部实现, 仅悲观锁相关方法使用 extra 参数.
    """

    @classmethod
    async def get_by_id_for_update(  # pyright: ignore[reportIncompatibleMethodOverride]
        cls,
        session: AsyncSession,
        entity_id: int,
        extra: SQLAExtra | None = None,
    ) -> AsyncSQLATableT | None:
        timeout = extra.lock_timeout if extra else None
        return await cls._get_by_id_for_update_core(session, entity_id, timeout=timeout)

    @classmethod
    async def batch_get_for_update(  # pyright: ignore[reportIncompatibleMethodOverride]
        cls,
        session: AsyncSession,
        entity_ids: Iterable[int],
        extra: SQLAExtra | None = None,
    ) -> list[AsyncSQLATableT]:
        timeout = extra.lock_timeout if extra else None
        return await cls._batch_get_for_update_core(session, entity_ids, timeout=timeout)

    @classmethod
    async def get_one_for_update(  # pyright: ignore[reportIncompatibleMethodOverride]
        cls,
        session: AsyncSession,
        extra: SQLAExtra | None = None,
        *,
        where_clauses: Any,
    ) -> AsyncSQLATableT | None:
        timeout = extra.lock_timeout if extra else None
        return await cls._get_one_for_update_core(session, where_clauses=where_clauses, timeout=timeout)


class AsyncWriteDALV2(  # pyright: ignore[reportIncompatibleMethodOverride]
    AsyncWriteDAL[AsyncSQLATableT, DTOModelT, CUModelT],
    AbstractAsyncWriteDAL[AsyncSession, AsyncSQLATableT, DTOModelT, CUModelT, SQLAExtra],
    AbstractAsyncAdvancedWriteDAL[AsyncSession, AsyncSQLATableT, CUModelT, SQLAExtra],
    Generic[AsyncSQLATableT, DTOModelT, CUModelT],
):
    """V2 异步写入 DAL — ABC 合规接口.

    与 V1 共享全部实现, 仅高级写操作使用 extra 参数.
    """

    @classmethod
    async def update_full_by_id(  # pyright: ignore[reportIncompatibleMethodOverride]
        cls,
        session: AsyncSession,
        entity_id: int,
        cu: CUModelT,
        extra: SQLAExtra | None = None,
    ) -> AsyncSQLATableT | None:
        need_refresh = extra.need_refresh if extra else False
        strict_missing = extra.strict_missing if extra else True
        return await cls._update_full_by_id_core(session, entity_id, cu, need_refresh=need_refresh, strict_missing=strict_missing)

    @classmethod
    async def update_partial_by_id(  # pyright: ignore[reportIncompatibleMethodOverride]
        cls,
        session: AsyncSession,
        entity_id: int,
        cu: CUModelT,
        extra: SQLAExtra | None = None,
    ) -> AsyncSQLATableT | None:
        if extra is None:
            return await cls._update_partial_by_id_core(session, entity_id, cu)
        return await cls._update_partial_by_id_core(
            session,
            entity_id,
            cu,
            need_refresh=extra.need_refresh,
            fields=extra.fields,
            none_policy=extra.none_policy,
            none_policy_overrides=extra.none_policy_overrides,
            strict=extra.strict,
        )

    @classmethod
    async def batch_update_by_conditions(  # pyright: ignore[reportIncompatibleMethodOverride]
        cls,
        session: AsyncSession,
        extra: SQLAExtra | None = None,
        *,
        conditions: Any,
        update_data: Any,
        updater_id: int | None = None,
    ) -> int:
        return await cls._batch_update_by_conditions_core(session, conditions=conditions, update_data=update_data, updater_id=updater_id)

    @classmethod
    async def batch_update_by_ids(  # pyright: ignore[reportIncompatibleMethodOverride]
        cls,
        session: AsyncSession,
        extra: SQLAExtra | None = None,
        *,
        entity_ids: set[int] | list[int],
        update_data: dict[InstrumentedAttribute[Any], Any],
        updater_id: int | None = None,
    ) -> int:
        filtered_ids = filtered_in_sql_values(entity_ids, int)
        if not filtered_ids:
            return 0
        _id_column = cls._Table.id  # pyright: ignore[reportAttributeAccessIssue,reportUnknownVariableType,reportUnknownMemberType]
        return await cls._batch_update_by_conditions_core(
            session,
            conditions=[_id_column.in_(filtered_ids)],  # pyright: ignore[reportUnknownMemberType]
            update_data=update_data,
            updater_id=updater_id,
        )


class AsyncBaseDALV2(  # pyright: ignore[reportIncompatibleMethodOverride]
    AsyncReadDALV2[AsyncSQLATableT, DTOModelT],
    AsyncWriteDALV2[AsyncSQLATableT, DTOModelT, CUModelT],
    AbstractAsyncLockDAL[AsyncSession, AsyncSQLATableT, CUModelT, SQLAExtra],
    AbstractAsyncRawSQLDAL[AsyncSession, SQLAExtra],
    Generic[AsyncSQLATableT, DTOModelT, CUModelT],
):
    """V2 异步完整 CRUD DAL — Read + Write + Lock + AdvancedWrite + BatchField + RawSQL."""

    @classmethod
    async def update_only_set_with_optimistic_lock(  # pyright: ignore[reportIncompatibleMethodOverride]
        cls,
        session: AsyncSession,
        entity_id: int,
        cu: CUModelT,
        extra: SQLAExtra | None = None,
        *,
        expected_version: int,
    ) -> AsyncSQLATableT | None:
        version_field = extra.version_field if extra else "version"
        need_refresh = extra.need_refresh if extra else False
        return await cls._update_only_set_with_optimistic_lock_core(
            session,
            entity_id,
            cu,
            expected_version=expected_version,
            need_refresh=need_refresh,
            version_field=version_field,
        )


__all__ = (
    "AsyncBaseDALV2",
    "AsyncReadDALV2",
    "AsyncWriteDALV2",
)
