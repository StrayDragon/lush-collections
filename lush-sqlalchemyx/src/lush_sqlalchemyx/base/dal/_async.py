"""异步 DAL 类及辅助工具.

包含从原 ``base/dal/__init__.py`` 中拆分出的全部异步专属代码.
需要 ``sqlalchemy[asyncio]`` 额外依赖; 模块顶层会在缺失时立即抛出 ``ImportError``.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import warnings
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, ParamSpec, TypeVar, cast

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy import ColumnExpressionArgument
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession
from sqlalchemy.orm import DeclarativeBase, InstrumentedAttribute, Mapped, mapped_column

from lush_sqlalchemyx._compat import require_async

from ._common import (
    OPTIMISTIC_LOCK_ERROR_MSG_TRAIT,
    PESSIMISTIC_LOCK_ERROR_MSG_TRAIT,
    READONLY_SESSION_FLAG,
    BaseModelT,
    CUModelT,
    DBRetryableError,
    DTOModelT,
    ReadOnlyMixin,
    RetryConfig,
    SoftDeleteTableMixin,
    SQLAlchemyOperationalError,
    T,
    _ensure_strict_fields,
    filtered_in_sql_values,
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
) -> AsyncIterator[None]:
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

AsyncSQLATableT = TypeVar("AsyncSQLATableT", bound="AsyncSqlATableBase")


class AsyncSqlATableBase(AsyncAttrs, DeclarativeBase):
    """异步 SQLAlchemy 表基类."""


class BasicAsyncBaseTable(AsyncSqlATableBase):
    """基础异步表类."""

    __abstract__ = True


class ReadOnlyBasicAsyncBaseTable(AsyncSqlATableBase, ReadOnlyMixin):
    """只读表基类."""

    __abstract__ = True


class StdAsyncBaseTable(BasicAsyncBaseTable, SoftDeleteTableMixin):
    """标准异步表类: 包含 id/时间戳/操作人/软删除等标准字段.

    .. deprecated::
        此类预设了特定业务字段, 下游应自行继承 ``BasicAsyncBaseTable`` 定义所需字段.
    """

    __abstract__ = True

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.__dict__.get("__abstract__", False):
            warnings.warn(
                f"{cls.__name__} 继承了已废弃的 StdAsyncBaseTable, 请改为直接继承 BasicAsyncBaseTable 并自行定义所需字段",
                DeprecationWarning,
                stacklevel=2,
            )

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    create_datetime: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime,
        nullable=False,
        comment="创建时间",
        server_default=sa.sql.func.now(),
        server_onupdate=sa.FetchedValue(),
    )

    create_operator_id: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        comment="创建人",
        default=0,
    )

    update_datetime: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime,
        nullable=True,
        comment="修改时间",
        server_default=sa.sql.func.now(),
        onupdate=sa.sql.func.now(),
        server_onupdate=sa.FetchedValue(),
    )
    update_operator_id: Mapped[int | None] = mapped_column(
        sa.Integer,
        nullable=True,
        comment="修改人",
    )


class StdReadOnlyBasicAsyncBaseTable(ReadOnlyBasicAsyncBaseTable):
    """标准只读异步表基类: 包含 id/时间戳/操作人等标准字段.

    .. deprecated::
        此类预设了特定业务字段, 下游应自行继承 ``ReadOnlyBasicAsyncBaseTable`` 定义所需字段.
    """

    __abstract__ = True

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.__dict__.get("__abstract__", False):
            warnings.warn(
                f"{cls.__name__} 继承了已废弃的 StdReadOnlyBasicAsyncBaseTable, 请改为直接继承 ReadOnlyBasicAsyncBaseTable 并自行定义所需字段",
                DeprecationWarning,
                stacklevel=2,
            )

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    create_datetime: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime,
        nullable=False,
        comment="创建时间",
        server_default=sa.sql.func.now(),
        server_onupdate=sa.FetchedValue(),
    )

    create_operator_id: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        comment="创建人",
        default=0,
    )

    update_datetime: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime,
        nullable=True,
        comment="修改时间",
        server_default=sa.sql.func.now(),
        onupdate=sa.sql.func.now(),
        server_onupdate=sa.FetchedValue(),
    )
    update_operator_id: Mapped[int | None] = mapped_column(
        sa.Integer,
        nullable=True,
        comment="修改人",
    )


# ---------------------------------------------------------------------------
# Async DAL hierarchy
# ---------------------------------------------------------------------------

ReadOnlyDTOModelT = TypeVar("ReadOnlyDTOModelT", bound=BaseModel)


class AsyncRawReadDAL:
    """原始只读数据访问层."""

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
    ) -> AsyncIterator[AsyncSQLATableT]:
        if not hasattr(table_class, "id") or not isinstance(getattr(table_class, "id", None), InstrumentedAttribute):
            raise ValueError(f"表 {table_class.__name__} 必须有 id 字段才能使用迭代方法")

        id_attr = cast("InstrumentedAttribute[Any]", getattr(table_class, "id"))  # noqa: B009

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


class AsyncReadDAL(AsyncRawReadDAL, Generic[AsyncSQLATableT, DTOModelT]):
    """抽象只读数据访问层基类."""

    _Table: ClassVar[type[AsyncSQLATableT]]  # pyright: ignore[reportGeneralTypeIssues]
    _DTO: ClassVar[type[DTOModelT]]  # pyright: ignore[reportGeneralTypeIssues]

    @classmethod
    async def get_by_id(
        cls,
        session: AsyncSession,
        entity_id: int,
    ) -> AsyncSQLATableT | None:
        return await session.get(cls._Table, entity_id)

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
        entity_ids: Iterable[int],
    ) -> dict[int, AsyncSQLATableT]:
        return await cls.batch_get_field__entity(
            session,
            field_name="id",
            field_values=entity_ids,
            field_value_type_as=int,
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
        entity_ids: Iterable[int],
    ) -> dict[int, DTOModelT]:
        return await cls.batch_get_field__dto(
            session,
            field_name="id",
            field_values=entity_ids,
        )

    @classmethod
    async def ret_dto_after_get_by_id(
        cls,
        session: AsyncSession,
        entity_id: int,
        need_refresh: bool = True,
    ) -> DTOModelT | None:
        entity = await session.get(cls._Table, entity_id)
        if entity:
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
    async def exists(cls, session: AsyncSession, entity_id: int) -> bool:
        entity = await session.get(cls._Table, entity_id)
        return entity is not None

    @classmethod
    async def _get_by_id_for_update_core(
        cls,
        session: AsyncSession,
        entity_id: int,
        *,
        timeout: int | None = None,
    ) -> AsyncSQLATableT | None:
        try:
            async with async_temp_set_lock_wait_timeout(session, timeout):
                stmt = (
                    sa.select(cls._Table)
                    .where(cls._Table.id == entity_id)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue, reportUnknownArgumentType]
                    .with_for_update()
                )
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
        except SQLAlchemyOperationalError as e:
            error_msg = str(e.orig) if hasattr(e, "orig") else str(e)
            if "Lock wait timeout exceeded" in error_msg or "1205" in error_msg:
                raise DBRetryableError(f"{PESSIMISTIC_LOCK_ERROR_MSG_TRAIT}-锁等待超时(entity_id={entity_id}): {error_msg}") from e
            raise

    @classmethod
    async def get_by_id_for_update(
        cls,
        session: AsyncSession,
        entity_id: int,
        *,
        lock_wait_timeout: int | None = None,
    ) -> AsyncSQLATableT | None:
        return await cls._get_by_id_for_update_core(session, entity_id, timeout=lock_wait_timeout)

    @classmethod
    async def _batch_get_for_update_core(
        cls,
        session: AsyncSession,
        entity_ids: Iterable[int],
        *,
        timeout: int | None = None,
    ) -> list[AsyncSQLATableT]:
        filtered_ids = filtered_in_sql_values(entity_ids, int)
        if not filtered_ids:
            return []

        try:
            async with async_temp_set_lock_wait_timeout(session, timeout):
                stmt = (
                    sa.select(cls._Table)
                    .where(cls._Table.id.in_(filtered_ids))  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue, reportUnknownArgumentType]
                    .with_for_update()
                )
                result = await session.execute(stmt)
                return list(result.scalars().all())
        except SQLAlchemyOperationalError as e:
            error_msg = str(e.orig) if hasattr(e, "orig") else str(e)
            if "Lock wait timeout exceeded" in error_msg or "1205" in error_msg:
                raise DBRetryableError(f"{PESSIMISTIC_LOCK_ERROR_MSG_TRAIT}-批量锁等待超时(entity_ids={filtered_ids}): {error_msg}") from e
            raise

    @classmethod
    async def batch_get_for_update(
        cls,
        session: AsyncSession,
        entity_ids: Iterable[int],
        *,
        lock_wait_timeout: int | None = None,
    ) -> list[AsyncSQLATableT]:
        return await cls._batch_get_for_update_core(session, entity_ids, timeout=lock_wait_timeout)

    @classmethod
    async def _get_one_for_update_core(
        cls,
        session: AsyncSession,
        *,
        where_clauses: list[ColumnExpressionArgument[bool]],
        timeout: int | None = None,
    ) -> AsyncSQLATableT | None:
        try:
            async with async_temp_set_lock_wait_timeout(session, timeout):
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
    async def get_one_for_update(
        cls,
        session: AsyncSession,
        *,
        where_clauses: list[ColumnExpressionArgument[bool]],
        lock_wait_timeout: int | None = None,
    ) -> AsyncSQLATableT | None:
        return await cls._get_one_for_update_core(session, where_clauses=where_clauses, timeout=lock_wait_timeout)

    @classmethod
    async def iter_record_dtos(
        cls,
        session: AsyncSession,
        *,
        where_clauses: list[ColumnExpressionArgument[bool]] | None = None,
        with_deleted: bool = False,
        batch_size: int = 500,
    ) -> AsyncIterator[DTOModelT]:
        async for entity in cls._iter_records(
            session,
            cls._Table,
            where_clauses=where_clauses,
            with_deleted=with_deleted,
            batch_size=batch_size,
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


class AsyncWriteDAL(AsyncRawDAL, AsyncRawReadDAL, Generic[AsyncSQLATableT, DTOModelT, CUModelT]):
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
        entity = cu.to_sqla_model()
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
        entity_id: int,
        cu: CUModelT,
        need_refresh: bool = False,
    ) -> AsyncSQLATableT | None:
        if session.info.get(READONLY_SESSION_FLAG):
            raise TypeError("当前会话被标记为只读, 不允许执行写入操作")
        entity = await session.get(cls._Table, entity_id)
        if not entity:
            return None

        update_data = cu.model_dump(exclude_unset=True, exclude={"id"})
        for key, value in update_data.items():
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
        entity_id: int,
        cu: CUModelT,
        need_refresh: bool = True,
    ) -> DTOModelT | None:
        entity = await cls.update_only_set_by_id(session, entity_id, cu, need_refresh)
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
    async def _update_full_by_id_core(
        cls,
        session: AsyncSession,
        entity_id: int,
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

        update_data: dict[str, Any] = cu.model_dump(exclude={"id"})

        if strict_missing:
            declared_fields = set(cu.__class__.model_fields.keys()) - {"id"}
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
    async def update_full_by_id(
        cls,
        session: AsyncSession,
        entity_id: int,
        cu: CUModelT,
        *,
        need_refresh: bool = False,
        strict_missing: bool = True,
    ) -> AsyncSQLATableT | None:
        return await cls._update_full_by_id_core(session, entity_id, cu, need_refresh=need_refresh, strict_missing=strict_missing)

    @classmethod
    async def _update_partial_by_id_core(
        cls,
        session: AsyncSession,
        entity_id: int,
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

        update_data: dict[str, Any] = cu.model_dump(exclude_unset=True, exclude={"id"})

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

            if value is None:
                field_policy = overrides_by_name.get(key, none_policy)
                if field_policy == "ignore":
                    continue
                if field_policy == "forbid":
                    raise ValueError(f"字段不允许置空: {key}")

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
        entity_id: int,
        cu: CUModelT,
        *,
        need_refresh: bool = False,
        fields: set[InstrumentedAttribute[Any]] | set[sa.Column[Any]] | None = None,
        none_policy: Literal["ignore", "allow", "forbid"] = "ignore",
        none_policy_overrides: dict[InstrumentedAttribute[Any] | sa.Column[Any], Literal["ignore", "allow", "forbid"]] | None = None,
        strict: bool = False,
    ) -> AsyncSQLATableT | None:
        return await cls._update_partial_by_id_core(
            session,
            entity_id,
            cu,
            need_refresh=need_refresh,
            fields=fields,
            none_policy=none_policy,
            none_policy_overrides=none_policy_overrides,
            strict=strict,
        )

    @classmethod
    async def delete_by_id(
        cls,
        session: AsyncSession,
        entity_id: int,
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
    ) -> AsyncIterator[AsyncSQLATableT]:
        async for entity in cls._iter_records(
            session,
            cls._Table,
            where_clauses=where_clauses,
            with_deleted=with_deleted,
            batch_size=batch_size,
        ):
            yield entity

    @classmethod
    async def _batch_update_by_conditions_core(
        cls,
        session: AsyncSession,
        *,
        conditions: list[ColumnExpressionArgument[bool]],
        update_data: dict[InstrumentedAttribute[Any], Any] | dict[sa.Column[Any], Any],
        updater_id: int | None = None,
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

        if hasattr(cls._Table, "update_datetime"):
            final_update_data["update_datetime"] = sa.sql.func.now()

        if hasattr(cls._Table, "update_operator_id") and updater_id is not None:
            final_update_data["update_operator_id"] = updater_id

        stmt = sa.update(cls._Table).where(*conditions).values(**final_update_data)

        result = await session.execute(stmt)
        await session.flush()

        return result.rowcount  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]

    @classmethod
    async def batch_update_by_conditions(
        cls,
        session: AsyncSession,
        *,
        whereclause: list[ColumnExpressionArgument[bool]],
        update_data: dict[InstrumentedAttribute[Any], Any] | dict[sa.Column[Any], Any],
        updater_id: int | None = None,
    ) -> int:
        return await cls._batch_update_by_conditions_core(session, conditions=whereclause, update_data=update_data, updater_id=updater_id)

    @classmethod
    async def batch_update_by_ids(
        cls,
        session: AsyncSession,
        *,
        entity_ids: set[int] | list[int],
        update_data: dict[InstrumentedAttribute[Any], Any] | dict[sa.Column[Any], Any],
        updater_id: int | None = None,
    ) -> int:
        filtered_ids = filtered_in_sql_values(entity_ids, int)
        if not filtered_ids:
            return 0
        _id_column = cls._Table.id  # pyright: ignore[reportAttributeAccessIssue,reportUnknownVariableType, reportUnknownMemberType]
        return await cls._batch_update_by_conditions_core(
            session,
            conditions=[_id_column.in_(filtered_ids)],  # pyright: ignore[reportUnknownMemberType]
            update_data=update_data,
            updater_id=updater_id,
        )

    @classmethod
    async def _update_only_set_with_optimistic_lock_core(
        cls,
        session: AsyncSession,
        entity_id: int,
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

        if not hasattr(cls._Table, "id"):
            raise AttributeError(f"表 {cls._Table.__name__} 不包含 id 字段,无法使用乐观锁")

        exclude_fields = {"id", version_field}
        update_data = cu.model_dump(exclude_unset=True, exclude=exclude_fields)

        if not update_data:
            return await session.get(cls._Table, entity_id)

        set_values: dict[str, Any] = {key: value for key, value in update_data.items() if hasattr(cls._Table, key)}

        if hasattr(cls._Table, "update_datetime"):
            set_values["update_datetime"] = sa.sql.func.now()

        version_field_value = getattr(cls._Table, version_field)
        set_values[version_field] = version_field_value + 1

        stmt = (
            sa.update(cls._Table)
            .where(cls._Table.id == entity_id)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue, reportUnknownArgumentType]
            .where(version_field_value == expected_version)
            .values(**set_values)
        )

        result = await session.execute(stmt)
        await session.flush()

        if result.rowcount > 0:  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
            entity = await session.get(cls._Table, entity_id)
            if need_refresh and entity:
                await session.refresh(entity)
            return entity

        raise DBRetryableError(f"{OPTIMISTIC_LOCK_ERROR_MSG_TRAIT}-版本号不匹配({entity_id=}, {expected_version=})")

    @classmethod
    async def update_only_set_with_optimistic_lock(
        cls,
        session: AsyncSession,
        entity_id: int,
        cu: CUModelT,
        *,
        expected_version: int,
        need_refresh: bool = False,
        version_field: str = "version",
    ) -> AsyncSQLATableT | None:
        return await cls._update_only_set_with_optimistic_lock_core(
            session,
            entity_id,
            cu,
            expected_version=expected_version,
            need_refresh=need_refresh,
            version_field=version_field,
        )


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
    "StdAsyncBaseTable",
    "StdReadOnlyBasicAsyncBaseTable",
    "async_temp_set_lock_wait_timeout",
    "async_with_retry",
)
