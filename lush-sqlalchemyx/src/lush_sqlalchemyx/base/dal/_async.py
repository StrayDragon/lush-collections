"""异步 DAL 类及辅助工具.

包含从原 ``base/dal/__init__.py`` 中拆分出的全部异步专属代码.
需要 ``sqlalchemy[asyncio]`` 额外依赖; 模块顶层会在缺失时立即抛出 ``ImportError``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, ParamSpec, TypeVar, cast

import sqlalchemy as sa
from lush_dal_protocol.abc import AbstractAsyncReadDAL, AbstractAsyncWriteDAL
from pydantic import BaseModel
from sqlalchemy import ColumnExpressionArgument
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession
from sqlalchemy.orm import DeclarativeBase, InstrumentedAttribute

from lush_sqlalchemyx._compat import require_async

from ._common import (
    OPTIMISTIC_LOCK_ERROR_MSG_TRAIT,
    PESSIMISTIC_LOCK_ERROR_MSG_TRAIT,
    READONLY_SESSION_FLAG,
    BaseModelT,
    CUModelT,
    DBRetryableError,
    DTOModelT,
    NonePolicy,
    ReadOnlyMixin,
    RetryConfig,
    SoftDeleteTableMixin,
    SQLAlchemyOperationalError,
    T,
    _apply_none_policy,
    _ensure_strict_fields,
    filtered_in_sql_values,
    resolve_pk_column,
    validate_orm_dal_pk_config,
)

if TYPE_CHECKING:
    from sqlalchemy.engine.interfaces import _CoreAnyExecuteParams  # pragma: no cover # pyright: ignore[reportPrivateUsage]

# --- Fast-fail if asyncio extras are unavailable ---
require_async()

_LOGGER = logging.getLogger(__name__)

P = ParamSpec("P")

# ---------------------------------------------------------------------------
# Async retry helpers
# ---------------------------------------------------------------------------


def async_with_retry(
    config: RetryConfig | None = None,
    *,
    on_conflict: Callable[[int, Exception], Awaitable[None]] | None = None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """数据库可重试异常统一重试装饰器"""
    retry_config = config or RetryConfig()

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception: Exception | None = None

            for attempt in range(1, retry_config.max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except DBRetryableError as e:  # noqa: PERF203
                    last_exception = e
                    error_type = type(e).__name__
                    _LOGGER.warning(
                        f"数据库操作冲突({error_type}),第{attempt}/{retry_config.max_attempts}次尝试失败: {func.__name__}, 原因: {e.message}"
                    )

                    if on_conflict:
                        try:
                            await on_conflict(attempt, e)
                        except Exception:
                            _LOGGER.exception("冲突回调执行失败")

                    if attempt < retry_config.max_attempts:
                        delay = retry_config.calculate_delay(attempt)
                        _LOGGER.debug(f"等待{delay:.3f}秒后重试...")
                        await asyncio.sleep(delay)
                    else:
                        _LOGGER.warning(f"数据库操作重试{retry_config.max_attempts}次后仍然失败: {func.__name__}")

            if last_exception:
                raise last_exception
            raise RuntimeError(f"重试失败但未捕获异常: {func.__name__}")

        return wrapper

    return decorator


@asynccontextmanager
async def async_temp_set_lock_wait_timeout(
    session: AsyncSession,
    timeout_seconds: int | None,
) -> AsyncGenerator[None, None]:
    """临时设置锁等待超时时间的上下文管理器"""
    if timeout_seconds is None:
        yield
        return

    try:
        with suppress(Exception):
            _ = await session.execute(sa.text(f"SET SESSION innodb_lock_wait_timeout = {timeout_seconds}"))
        yield
    finally:
        with suppress(Exception):
            _ = await session.execute(sa.text("SET SESSION innodb_lock_wait_timeout = DEFAULT"))


# ---------------------------------------------------------------------------
# Async Table bases
# ---------------------------------------------------------------------------

# 隐含约束: AsyncSQLATableT 应为 AsyncSqlATableBase (AsyncAttrs + DeclarativeBase) 子类.
AsyncSQLATableT = TypeVar("AsyncSQLATableT")


class AsyncSqlATableBase(AsyncAttrs, DeclarativeBase):
    """异步 SQLAlchemy 表基类."""


class BasicAsyncBaseTable(AsyncSqlATableBase):
    """基础异步表类."""

    __abstract__ = True


class ReadOnlyBasicAsyncBaseTable(AsyncSqlATableBase, ReadOnlyMixin):
    """只读表基类."""

    __abstract__ = True


# ---------------------------------------------------------------------------
# Async DAL hierarchy
# ---------------------------------------------------------------------------

ReadOnlyDTOModelT = TypeVar("ReadOnlyDTOModelT", bound=BaseModel)


class AsyncRawReadDAL:
    """原始只读数据访问层."""

    _pk_attr: ClassVar[str] = "id"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        validate_orm_dal_pk_config(cls)

    @classmethod
    def _pk_column(cls) -> InstrumentedAttribute[Any]:
        """返回本 DAL 绑定表的主键列."""
        return resolve_pk_column(cls._Table, cls._pk_attr)  # pyright: ignore[reportAttributeAccessIssue]

    @classmethod
    async def execute_readonly_sql(
        cls,
        session: AsyncSession,
        sql: str | sa.TextClause,
        params: _CoreAnyExecuteParams | None = None,
    ) -> sa.Result[Any]:
        if params is None:
            params = {}

        stmt = sql if isinstance(sql, sa.TextClause) else sa.text(sql)

        sql_str = str(stmt).upper().strip()
        write_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE", "REPLACE"]
        for keyword in write_keywords:
            if sql_str.startswith(keyword):
                raise RuntimeError(f"只读DAL不允许执行写入操作SQL: {keyword}")

        return await session.execute(stmt, params)

    @classmethod
    async def _iter_records(
        cls,
        session: AsyncSession,
        table_class: type[AsyncSQLATableT],
        *,
        where_clauses: list[ColumnExpressionArgument[bool]] | None = None,
        with_deleted: bool = False,
        batch_size: int = 500,
        pk_attr: str = "id",
    ) -> AsyncGenerator[AsyncSQLATableT, None]:
        try:
            id_attr = resolve_pk_column(table_class, pk_attr)
        except AttributeError as e:
            raise ValueError(f"表 {table_class.__name__} 必须有主键字段 {pk_attr!r} 才能使用迭代方法") from e

        last_id: Any = None

        while True:
            stmt = sa.select(table_class)

            if where_clauses:
                for clause in where_clauses:
                    stmt = stmt.where(clause)

            if last_id is not None:
                stmt = stmt.where(id_attr < last_id)

            stmt = stmt.order_by(id_attr.desc())
            stmt = stmt.limit(batch_size)

            if with_deleted:
                stmt = stmt.execution_options(include_soft_deleted=True)

            result = await session.execute(stmt)
            batch = result.scalars().all()

            if not batch:
                break

            for entity in batch:
                yield entity

            last_id = getattr(batch[-1], id_attr.key)


class AsyncReadDAL(
    AsyncRawReadDAL,
    AbstractAsyncReadDAL[AsyncSession, AsyncSQLATableT, DTOModelT, int],
    Generic[AsyncSQLATableT, DTOModelT],
):
    """抽象只读数据访问层基类."""

    _Table: ClassVar[type[AsyncSQLATableT]]  # pyright: ignore[reportGeneralTypeIssues]
    _DTO: ClassVar[type[DTOModelT]]  # pyright: ignore[reportGeneralTypeIssues]

    @classmethod
    async def get_by_id(
        cls,
        session: AsyncSession,
        entity_id: Any,
    ) -> AsyncSQLATableT | None:
        entity = await session.get(cls._Table, entity_id)
        if entity is not None and isinstance(entity, SoftDeleteTableMixin) and entity.is_soft_deleted:
            return None
        return entity

    @classmethod
    async def batch_get_field__entity(
        cls,
        session: AsyncSession,
        *,
        field_name: str,
        field_values: Iterable[T],
        field_value_type_as: Callable[[T], T] = lambda x: x,
    ) -> dict[T, AsyncSQLATableT]:
        filtered_field_values = filtered_in_sql_values(
            field_values,
            field_value_type_as,
        )
        if not filtered_field_values:
            return {}
        stmt = sa.select(cls._Table).where(getattr(cls._Table, field_name).in_(filtered_field_values))
        result = await session.execute(stmt)
        return {getattr(row, field_name): row for row in result.scalars().all()}

    @classmethod
    async def batch_get_id__entity(
        cls,
        session: AsyncSession,
        entity_ids: Iterable[Any],
    ) -> dict[Any, AsyncSQLATableT]:
        return await cls.batch_get_field__entity(
            session,
            field_name=cls._pk_attr,
            field_values=entity_ids,
        )

    @classmethod
    async def batch_get_field__dto(
        cls,
        session: AsyncSession,
        *,
        field_name: str,
        field_values: Iterable[T],
    ) -> dict[T, DTOModelT]:
        return {
            field_value: cls._DTO.model_validate(entity)
            for field_value, entity in (
                await cls.batch_get_field__entity(
                    session,
                    field_name=field_name,
                    field_values=field_values,
                )
            ).items()
        }

    @classmethod
    async def batch_get_id__dto(
        cls,
        session: AsyncSession,
        entity_ids: Iterable[Any],
    ) -> dict[Any, DTOModelT]:
        return await cls.batch_get_field__dto(
            session,
            field_name=cls._pk_attr,
            field_values=entity_ids,
        )

    @classmethod
    async def ret_dto_after_get_by_id(
        cls,
        session: AsyncSession,
        entity_id: Any,
        need_refresh: bool = True,
    ) -> DTOModelT | None:
        entity = await session.get(cls._Table, entity_id)
        if entity:
            if isinstance(entity, SoftDeleteTableMixin) and entity.is_soft_deleted:
                return None
            if need_refresh:
                await session.refresh(entity)
            return cls._DTO.model_validate(entity)
        return None

    @classmethod
    async def get_all(cls, session: AsyncSession, skip: int = 0, limit: int = 100) -> list[DTOModelT]:
        stmt = sa.select(cls._Table).offset(skip).limit(limit)
        result = await session.execute(stmt)
        entities = result.scalars().all()
        return [cls._DTO.model_validate(entity) for entity in entities]

    @classmethod
    async def count(cls, session: AsyncSession) -> int:
        stmt = sa.select(sa.func.count()).select_from(cls._Table)
        result = await session.execute(stmt)
        return result.scalar() or 0

    @classmethod
    async def exists(cls, session: AsyncSession, entity_id: Any) -> bool:
        entity = await session.get(cls._Table, entity_id)
        if entity is None:
            return False
        return not (isinstance(entity, SoftDeleteTableMixin) and entity.is_soft_deleted)

    @classmethod
    async def get_by_id_for_update(
        cls,
        session: AsyncSession,
        entity_id: Any,
        *,
        lock_wait_timeout: int | None = None,
    ) -> AsyncSQLATableT | None:
        try:
            async with async_temp_set_lock_wait_timeout(session, lock_wait_timeout):
                stmt = sa.select(cls._Table).where(cls._pk_column() == entity_id).with_for_update()
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
        except SQLAlchemyOperationalError as e:
            error_msg = str(e.orig) if hasattr(e, "orig") else str(e)
            if "Lock wait timeout exceeded" in error_msg or "1205" in error_msg:
                raise DBRetryableError(f"{PESSIMISTIC_LOCK_ERROR_MSG_TRAIT}-锁等待超时(entity_id={entity_id}): {error_msg}") from e
            raise

    @classmethod
    async def batch_get_for_update(
        cls,
        session: AsyncSession,
        entity_ids: Iterable[Any],
        *,
        lock_wait_timeout: int | None = None,
    ) -> list[AsyncSQLATableT]:
        filtered_ids = filtered_in_sql_values(entity_ids)
        if not filtered_ids:
            return []

        try:
            async with async_temp_set_lock_wait_timeout(session, lock_wait_timeout):
                stmt = sa.select(cls._Table).where(cls._pk_column().in_(filtered_ids)).with_for_update()
                result = await session.execute(stmt)
                return list(result.scalars().all())
        except SQLAlchemyOperationalError as e:
            error_msg = str(e.orig) if hasattr(e, "orig") else str(e)
            if "Lock wait timeout exceeded" in error_msg or "1205" in error_msg:
                raise DBRetryableError(f"{PESSIMISTIC_LOCK_ERROR_MSG_TRAIT}-批量锁等待超时(entity_ids={filtered_ids}): {error_msg}") from e
            raise

    @classmethod
    async def get_one_for_update(
        cls,
        session: AsyncSession,
        *,
        where_clauses: list[ColumnExpressionArgument[bool]],
        lock_wait_timeout: int | None = None,
    ) -> AsyncSQLATableT | None:
        try:
            async with async_temp_set_lock_wait_timeout(session, lock_wait_timeout):
                stmt = sa.select(cls._Table).with_for_update()

                for clause in where_clauses:
                    stmt = stmt.where(clause)

                result = await session.execute(stmt)
                return result.scalar_one_or_none()
        except SQLAlchemyOperationalError as e:
            error_msg = str(e.orig) if hasattr(e, "orig") else str(e)
            if "Lock wait timeout exceeded" in error_msg or "1205" in error_msg:
                raise DBRetryableError(f"{PESSIMISTIC_LOCK_ERROR_MSG_TRAIT}-条件锁等待超时: {error_msg}") from e
            raise

    @classmethod
    async def iter_record_dtos(
        cls,
        session: AsyncSession,
        *,
        where_clauses: list[ColumnExpressionArgument[bool]] | None = None,
        with_deleted: bool = False,
        batch_size: int = 500,
    ) -> AsyncGenerator[DTOModelT, None]:
        async for entity in cls._iter_records(
            session,
            cls._Table,
            where_clauses=where_clauses,
            with_deleted=with_deleted,
            batch_size=batch_size,
            pk_attr=cls._pk_attr,
        ):
            yield cls._DTO.model_validate(entity)


class AsyncRawDAL:
    """原始数据访问层."""

    @classmethod
    async def execute_sql(
        cls,
        session: AsyncSession,
        sql: str | sa.TextClause,
        params: _CoreAnyExecuteParams | None = None,
    ) -> sa.Result[Any]:
        if params is None:
            params = {}

        stmt = sql if isinstance(sql, sa.TextClause) else sa.text(sql)
        return await session.execute(stmt, params)


class AsyncWriteDAL(
    AsyncRawDAL,
    AsyncRawReadDAL,
    AbstractAsyncWriteDAL[AsyncSession, AsyncSQLATableT, DTOModelT, CUModelT, int],
    Generic[AsyncSQLATableT, DTOModelT, CUModelT],
):
    """写入数据访问层基类."""

    _Table: ClassVar[type[AsyncSQLATableT]]  # pyright: ignore[reportGeneralTypeIssues]
    _DTO: ClassVar[type[DTOModelT]]  # pyright: ignore[reportGeneralTypeIssues]
    _CU: ClassVar[type[CUModelT]]  # pyright: ignore[reportGeneralTypeIssues]

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        cu: CUModelT,
        need_refresh: bool = True,
    ) -> AsyncSQLATableT:
        if session.info.get(READONLY_SESSION_FLAG):
            raise TypeError("当前会话被标记为只读, 不允许执行写入操作")
        entity = cu.to_orm_model()
        session.add(entity)
        await session.flush()
        if need_refresh:
            await session.refresh(entity)
        return cast("AsyncSQLATableT", entity)

    @classmethod
    async def ret_dto_after_create(
        cls,
        session: AsyncSession,
        cu: CUModelT,
        need_refresh: bool = True,
    ) -> DTOModelT:
        entity = await cls.create(session, cu, need_refresh)
        return cls._DTO.model_validate(entity)

    @classmethod
    async def update_only_set_by_id(
        cls,
        session: AsyncSession,
        entity_id: Any,
        cu: CUModelT,
        need_refresh: bool = False,
        *,
        none_policy: NonePolicy = "allow",
    ) -> AsyncSQLATableT | None:
        """仅更新 CU 中已设置 (非 unset) 的字段.

        ``none_policy`` 控制显式传入的 ``None`` 如何处理, 详见 ``NonePolicy``:

        - ``allow`` (默认): 写入 SQL ``NULL``, 与 0.7.0 及更早版本行为一致
        - ``ignore``: 跳过 ``None``, 保留库中原值 — 迁移全字段 CU 时推荐显式传入
        - ``forbid``: 遇到 ``None`` 抛 ``ValueError``
        """
        if session.info.get(READONLY_SESSION_FLAG):
            raise TypeError("当前会话被标记为只读, 不允许执行写入操作")
        entity = await session.get(cls._Table, entity_id)
        if not entity:
            return None

        update_exclude = type(cu).resolve_cu_config()["update_exclude"]
        update_data = cu.model_dump(exclude_unset=True, exclude=set(update_exclude))
        for key, value in update_data.items():
            if not _apply_none_policy(key, value, none_policy=none_policy):
                continue
            if hasattr(entity, key):
                setattr(entity, key, value)

        await session.flush()
        if need_refresh:
            await session.refresh(entity)
        return entity

    @classmethod
    async def ret_dto_after_update_by_id(
        cls,
        session: AsyncSession,
        entity_id: Any,
        cu: CUModelT,
        need_refresh: bool = True,
        *,
        none_policy: NonePolicy = "allow",
    ) -> DTOModelT | None:
        entity = await cls.update_only_set_by_id(session, entity_id, cu, need_refresh, none_policy=none_policy)
        if entity:
            return cls._DTO.model_validate(entity)
        return None

    @staticmethod
    def _ensure_strict_fields(
        *,
        provided_keys: set[str],
        allowed_names: set[str] | None,
        strict: bool,
    ) -> None:
        _ensure_strict_fields(provided_keys=provided_keys, allowed_names=allowed_names, strict=strict)

    @classmethod
    async def update_full_by_id(
        cls,
        session: AsyncSession,
        entity_id: Any,
        cu: CUModelT,
        *,
        need_refresh: bool = False,
        strict_missing: bool = True,
    ) -> AsyncSQLATableT | None:
        if session.info.get(READONLY_SESSION_FLAG):
            raise TypeError("当前会话被标记为只读, 不允许执行写入操作")

        entity = await session.get(cls._Table, entity_id)
        if not entity:
            return None

        update_exclude = type(cu).resolve_cu_config()["update_exclude"]
        update_data: dict[str, Any] = cu.model_dump(exclude=set(update_exclude))

        if strict_missing:
            declared_fields = set(cu.__class__.model_fields.keys()) - set(update_exclude)
            missing_declared = [k for k in declared_fields if k not in update_data]
            if missing_declared:
                raise ValueError(f"缺少必须字段: {missing_declared}")

        for key, value in update_data.items():
            if hasattr(entity, key):
                setattr(entity, key, value)

        await session.flush()
        if need_refresh:
            await session.refresh(entity)
        return entity

    @classmethod
    async def update_partial_by_id(
        cls,
        session: AsyncSession,
        entity_id: Any,
        cu: CUModelT,
        *,
        need_refresh: bool = False,
        fields: set[InstrumentedAttribute[Any]] | set[sa.Column[Any]] | None = None,
        none_policy: Literal["ignore", "allow", "forbid"] = "ignore",
        none_policy_overrides: dict[InstrumentedAttribute[Any] | sa.Column[Any], Literal["ignore", "allow", "forbid"]] | None = None,
        strict: bool = False,
    ) -> AsyncSQLATableT | None:
        if session.info.get(READONLY_SESSION_FLAG):
            raise TypeError("当前会话被标记为只读, 不允许执行写入操作")

        entity = await session.get(cls._Table, entity_id)
        if not entity:  # pragma: no branch
            return None  # pragma: no cover  # coverage.py 异步协程计量局限; 逻辑已由测试覆盖

        update_exclude = type(cu).resolve_cu_config()["update_exclude"]
        update_data: dict[str, Any] = cu.model_dump(exclude_unset=True, exclude=set(update_exclude))

        allowed_names: set[str] | None = None
        if fields is not None:
            allowed_names = set()
            for f in fields:
                if isinstance(f, InstrumentedAttribute):
                    allowed_names.add(f.key)
                elif isinstance(f, sa.Column):
                    allowed_names.add(f.name)
                else:
                    allowed_names.add(str(f))

        overrides_by_name: dict[str, Literal["ignore", "allow", "forbid"]] = {}
        if none_policy_overrides:
            for f, pol in none_policy_overrides.items():
                if isinstance(f, InstrumentedAttribute):
                    overrides_by_name[f.key] = pol
                elif isinstance(f, sa.Column):
                    overrides_by_name[f.name] = pol
                else:
                    overrides_by_name[str(f)] = pol

        cls._ensure_strict_fields(
            provided_keys=set(update_data.keys()),
            allowed_names=allowed_names,
            strict=strict,
        )

        for key, value in list(update_data.items()):
            if allowed_names is not None and key not in allowed_names:
                continue

            field_policy = overrides_by_name.get(key, none_policy)
            if not _apply_none_policy(key, value, none_policy=field_policy):
                continue

            if hasattr(entity, key):
                setattr(entity, key, value)

        await session.flush()
        if need_refresh:
            await session.refresh(entity)
        return entity

    @classmethod
    async def delete_by_id(
        cls,
        session: AsyncSession,
        entity_id: Any,
    ) -> bool:
        if session.info.get(READONLY_SESSION_FLAG):
            raise TypeError("当前会话被标记为只读, 不允许执行写入操作")
        entity = await session.get(cls._Table, entity_id)
        if not entity:
            return False

        await session.delete(entity)
        await session.flush()
        return True

    @classmethod
    async def iter_records(
        cls,
        session: AsyncSession,
        *,
        where_clauses: list[ColumnExpressionArgument[bool]] | None = None,
        with_deleted: bool = False,
        batch_size: int = 500,
    ) -> AsyncGenerator[AsyncSQLATableT, None]:
        async for entity in cls._iter_records(
            session,
            cls._Table,
            where_clauses=where_clauses,
            with_deleted=with_deleted,
            batch_size=batch_size,
            pk_attr=cls._pk_attr,
        ):
            yield entity

    @classmethod
    async def batch_update_by_conditions(
        cls,
        session: AsyncSession,
        *,
        whereclause: list[ColumnExpressionArgument[bool]],
        update_data: dict[InstrumentedAttribute[Any], Any] | dict[sa.Column[Any], Any],
    ) -> int:
        if session.info.get(READONLY_SESSION_FLAG):
            raise TypeError("当前会话被标记为只读, 不允许执行写入操作")

        final_update_data: dict[str, Any] = {}

        for key, value in update_data.items():
            if isinstance(key, sa.Column):
                final_update_data[key.name] = value
            elif isinstance(key, InstrumentedAttribute):
                final_update_data[key.key] = value
            elif isinstance(key, str):
                final_update_data[str(key)] = value
            else:
                raise ValueError(f"不支持的更新条件类型: {type(key)}")

        stmt = sa.update(cls._Table).where(*whereclause).values(**final_update_data)

        result = await session.execute(stmt)
        await session.flush()

        return result.rowcount  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]

    @classmethod
    async def batch_update_by_ids(
        cls,
        session: AsyncSession,
        *,
        entity_ids: set[Any] | list[Any],
        update_data: dict[InstrumentedAttribute[Any], Any] | dict[sa.Column[Any], Any],
    ) -> int:
        filtered_ids = filtered_in_sql_values(entity_ids)
        if not filtered_ids:
            return 0
        return await cls.batch_update_by_conditions(
            session,
            whereclause=[cls._pk_column().in_(filtered_ids)],
            update_data=update_data,
        )

    @classmethod
    async def update_only_set_with_optimistic_lock(
        cls,
        session: AsyncSession,
        entity_id: Any,
        cu: CUModelT,
        *,
        expected_version: int,
        need_refresh: bool = False,
        version_field: str = "version",
    ) -> AsyncSQLATableT | None:
        if session.info.get(READONLY_SESSION_FLAG):
            raise TypeError("当前会话被标记为只读, 不允许执行写入操作")

        if not hasattr(cls._Table, version_field):
            raise AttributeError(f"表 {cls._Table.__name__} 不包含 {version_field} 字段,无法使用乐观锁")

        pk_col = cls._pk_column()

        exclude_fields = type(cu).resolve_cu_config()["update_exclude"] | {version_field}
        update_data = cu.model_dump(exclude_unset=True, exclude=set(exclude_fields))

        if not update_data:
            return await session.get(cls._Table, entity_id)

        set_values: dict[str, Any] = {key: value for key, value in update_data.items() if hasattr(cls._Table, key)}

        version_field_value = getattr(cls._Table, version_field)
        set_values[version_field] = version_field_value + 1

        stmt = sa.update(cls._Table).where(pk_col == entity_id).where(version_field_value == expected_version).values(**set_values)

        result = await session.execute(stmt)
        await session.flush()

        if result.rowcount > 0:  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
            entity = await session.get(cls._Table, entity_id)
            if need_refresh and entity:
                await session.refresh(entity)
            return entity

        raise DBRetryableError(f"{OPTIMISTIC_LOCK_ERROR_MSG_TRAIT}-版本号不匹配({entity_id=}, {expected_version=})")


class AsyncXDALOp(AsyncRawReadDAL, AsyncRawDAL):
    """扩展数据访问操作类."""


class AsyncBaseDAL(AsyncReadDAL[AsyncSQLATableT, DTOModelT], AsyncWriteDAL[AsyncSQLATableT, DTOModelT, CUModelT]):
    """基础数据访问层."""


class ReadOnlyAsyncBaseDAL(AsyncReadDAL[AsyncSQLATableT, ReadOnlyDTOModelT]):
    """只读数据访问层基类."""

    @classmethod
    def _get_dto_fields(cls, dto_class: type[BaseModelT]) -> list[str]:
        return list(dto_class.model_fields.keys())


__all__ = (
    "AsyncBaseDAL",
    "AsyncRawDAL",
    "AsyncRawReadDAL",
    "AsyncReadDAL",
    "AsyncSQLATableT",
    "AsyncSqlATableBase",
    "AsyncWriteDAL",
    "AsyncXDALOp",
    "BasicAsyncBaseTable",
    "ReadOnlyAsyncBaseDAL",
    "ReadOnlyBasicAsyncBaseTable",
    "async_temp_set_lock_wait_timeout",
    "async_with_retry",
)
