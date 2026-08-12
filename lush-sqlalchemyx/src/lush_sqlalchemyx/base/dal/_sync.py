"""同步 DAL 类及辅助工具 — ``_async.py`` 的同步镜像.

本模块 **不需要** ``sqlalchemy[asyncio]``; 仅使用 SQLAlchemy 2.x 标准同步 API
(``Session``、``Engine``、``create_engine`` 等).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Generator, Iterable
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, ParamSpec, TypeVar, cast

import sqlalchemy as sa
from lush_dal_protocol.abc import AbstractSyncReadDAL, AbstractSyncWriteDAL
from pydantic import BaseModel
from sqlalchemy import ColumnExpressionArgument
from sqlalchemy.orm import DeclarativeBase, InstrumentedAttribute, Session

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
)

if TYPE_CHECKING:
    from sqlalchemy.engine.interfaces import _CoreAnyExecuteParams  # pragma: no cover # pyright: ignore[reportPrivateUsage]

_LOGGER = logging.getLogger(__name__)

P = ParamSpec("P")

# ---------------------------------------------------------------------------
# Sync retry helpers
# ---------------------------------------------------------------------------


def sync_with_retry(
    config: RetryConfig | None = None,
    *,
    on_conflict: Callable[[int, Exception], None] | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """数据库可重试异常统一重试装饰器 (同步版)"""
    retry_config = config or RetryConfig()

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception: Exception | None = None

            for attempt in range(1, retry_config.max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except DBRetryableError as e:  # noqa: PERF203
                    last_exception = e
                    error_type = type(e).__name__
                    _LOGGER.warning(
                        f"数据库操作冲突({error_type}),第{attempt}/{retry_config.max_attempts}次尝试失败: {func.__name__}, 原因: {e.message}"
                    )

                    if on_conflict:
                        try:
                            on_conflict(attempt, e)
                        except Exception:
                            _LOGGER.exception("冲突回调执行失败")

                    if attempt < retry_config.max_attempts:
                        delay = retry_config.calculate_delay(attempt)
                        _LOGGER.debug(f"等待{delay:.3f}秒后重试...")
                        time.sleep(delay)
                    else:
                        _LOGGER.warning(f"数据库操作重试{retry_config.max_attempts}次后仍然失败: {func.__name__}")

            if last_exception:
                raise last_exception
            raise RuntimeError(f"重试失败但未捕获异常: {func.__name__}")  # pragma: no cover

        return wrapper

    return decorator


@contextmanager
def sync_temp_set_lock_wait_timeout(
    session: Session,
    timeout_seconds: int | None,
) -> Generator[None, None, None]:
    """临时设置锁等待超时时间的上下文管理器 (同步版)"""
    if timeout_seconds is None:
        yield
        return

    try:
        with suppress(Exception):
            _ = session.execute(sa.text(f"SET SESSION innodb_lock_wait_timeout = {timeout_seconds}"))
        yield
    finally:
        with suppress(Exception):
            _ = session.execute(sa.text("SET SESSION innodb_lock_wait_timeout = DEFAULT"))


# ---------------------------------------------------------------------------
# Sync Table bases
# ---------------------------------------------------------------------------

# 隐含约束: SyncSQLATableT 应为 DeclarativeBase 子类 (含 Flask-SQLAlchemy db.Model).
SyncSQLATableT = TypeVar("SyncSQLATableT")


class SyncSqlATableBase(DeclarativeBase):
    """同步 SQLAlchemy 表基类 — 无 AsyncAttrs."""


class BasicSyncBaseTable(SyncSqlATableBase):
    """基础同步表类."""

    __abstract__ = True


class ReadOnlySyncBaseTable(SyncSqlATableBase, ReadOnlyMixin):
    """只读同步表基类."""

    __abstract__ = True


# ---------------------------------------------------------------------------
# Sync DAL hierarchy
# ---------------------------------------------------------------------------

ReadOnlyDTOModelT = TypeVar("ReadOnlyDTOModelT", bound=BaseModel)


class SyncRawReadDAL:
    """原始只读数据访问层 (同步版)."""

    _pk_attr: ClassVar[str] = "id"

    @classmethod
    def _pk_column(cls) -> InstrumentedAttribute[Any]:
        """返回本 DAL 绑定表的主键列."""
        return resolve_pk_column(cls._Table, cls._pk_attr)  # pyright: ignore[reportAttributeAccessIssue]

    @classmethod
    def execute_readonly_sql(
        cls,
        session: Session,
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

        return session.execute(stmt, params)

    @classmethod
    def _iter_records(
        cls,
        session: Session,
        table_class: type[SyncSQLATableT],
        *,
        where_clauses: list[ColumnExpressionArgument[bool]] | None = None,
        with_deleted: bool = False,
        batch_size: int = 500,
        pk_attr: str = "id",
    ) -> Generator[SyncSQLATableT, None, None]:
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

            result = session.execute(stmt)
            batch = result.scalars().all()

            if not batch:
                break

            yield from batch

            last_id = getattr(batch[-1], id_attr.key)


class SyncReadDAL(
    SyncRawReadDAL,
    AbstractSyncReadDAL[Session, SyncSQLATableT, DTOModelT, int],
    Generic[SyncSQLATableT, DTOModelT],
):
    """抽象只读数据访问层基类 (同步版)."""

    _Table: ClassVar[type[SyncSQLATableT]]  # pyright: ignore[reportGeneralTypeIssues]
    _DTO: ClassVar[type[DTOModelT]]  # pyright: ignore[reportGeneralTypeIssues]

    @classmethod
    def get_by_id(
        cls,
        session: Session,
        entity_id: Any,
    ) -> SyncSQLATableT | None:
        entity = session.get(cls._Table, entity_id)
        if entity is not None and isinstance(entity, SoftDeleteTableMixin) and entity.is_soft_deleted:
            return None
        return entity

    @classmethod
    def batch_get_field__entity(
        cls,
        session: Session,
        *,
        field_name: str,
        field_values: Iterable[T],
        field_value_type_as: Callable[[T], T] = lambda x: x,
    ) -> dict[T, SyncSQLATableT]:
        filtered_field_values = filtered_in_sql_values(
            field_values,
            field_value_type_as,
        )
        if not filtered_field_values:
            return {}
        stmt = sa.select(cls._Table).where(getattr(cls._Table, field_name).in_(filtered_field_values))
        result = session.execute(stmt)
        return {getattr(row, field_name): row for row in result.scalars().all()}

    @classmethod
    def batch_get_id__entity(
        cls,
        session: Session,
        entity_ids: Iterable[Any],
    ) -> dict[Any, SyncSQLATableT]:
        return cls.batch_get_field__entity(
            session,
            field_name=cls._pk_attr,
            field_values=entity_ids,
        )

    @classmethod
    def batch_get_field__dto(
        cls,
        session: Session,
        *,
        field_name: str,
        field_values: Iterable[T],
    ) -> dict[T, DTOModelT]:
        return {
            field_value: cls._DTO.model_validate(entity)
            for field_value, entity in cls.batch_get_field__entity(
                session,
                field_name=field_name,
                field_values=field_values,
            ).items()
        }

    @classmethod
    def batch_get_id__dto(
        cls,
        session: Session,
        entity_ids: Iterable[Any],
    ) -> dict[Any, DTOModelT]:
        return cls.batch_get_field__dto(
            session,
            field_name=cls._pk_attr,
            field_values=entity_ids,
        )

    @classmethod
    def ret_dto_after_get_by_id(
        cls,
        session: Session,
        entity_id: Any,
        need_refresh: bool = True,
    ) -> DTOModelT | None:
        entity = session.get(cls._Table, entity_id)
        if entity:
            if isinstance(entity, SoftDeleteTableMixin) and entity.is_soft_deleted:
                return None
            if need_refresh:
                session.refresh(entity)
            return cls._DTO.model_validate(entity)
        return None

    @classmethod
    def get_all(cls, session: Session, skip: int = 0, limit: int = 100) -> list[DTOModelT]:
        stmt = sa.select(cls._Table).offset(skip).limit(limit)
        result = session.execute(stmt)
        entities = result.scalars().all()
        return [cls._DTO.model_validate(entity) for entity in entities]

    @classmethod
    def count(cls, session: Session) -> int:
        stmt = sa.select(sa.func.count()).select_from(cls._Table)
        result = session.execute(stmt)
        return result.scalar() or 0

    @classmethod
    def exists(cls, session: Session, entity_id: Any) -> bool:
        entity = session.get(cls._Table, entity_id)
        if entity is None:
            return False
        return not (isinstance(entity, SoftDeleteTableMixin) and entity.is_soft_deleted)

    @classmethod
    def get_by_id_for_update(
        cls,
        session: Session,
        entity_id: Any,
        *,
        lock_wait_timeout: int | None = None,
    ) -> SyncSQLATableT | None:
        try:
            with sync_temp_set_lock_wait_timeout(session, lock_wait_timeout):
                stmt = sa.select(cls._Table).where(cls._pk_column() == entity_id).with_for_update()
                result = session.execute(stmt)
                return result.scalar_one_or_none()
        except SQLAlchemyOperationalError as e:
            error_msg = str(e.orig) if hasattr(e, "orig") else str(e)
            if "Lock wait timeout exceeded" in error_msg or "1205" in error_msg:
                raise DBRetryableError(f"{PESSIMISTIC_LOCK_ERROR_MSG_TRAIT}-锁等待超时(entity_id={entity_id}): {error_msg}") from e
            raise

    @classmethod
    def batch_get_for_update(
        cls,
        session: Session,
        entity_ids: Iterable[Any],
        *,
        lock_wait_timeout: int | None = None,
    ) -> list[SyncSQLATableT]:
        filtered_ids = filtered_in_sql_values(entity_ids)
        if not filtered_ids:
            return []
        try:
            with sync_temp_set_lock_wait_timeout(session, lock_wait_timeout):
                stmt = sa.select(cls._Table).where(cls._pk_column().in_(filtered_ids)).with_for_update()
                result = session.execute(stmt)
                return list(result.scalars().all())
        except SQLAlchemyOperationalError as e:
            error_msg = str(e.orig) if hasattr(e, "orig") else str(e)
            if "Lock wait timeout exceeded" in error_msg or "1205" in error_msg:
                raise DBRetryableError(f"{PESSIMISTIC_LOCK_ERROR_MSG_TRAIT}-批量锁等待超时(entity_ids={filtered_ids}): {error_msg}") from e
            raise

    @classmethod
    def get_one_for_update(
        cls,
        session: Session,
        *,
        where_clauses: list[ColumnExpressionArgument[bool]],
        lock_wait_timeout: int | None = None,
    ) -> SyncSQLATableT | None:
        try:
            with sync_temp_set_lock_wait_timeout(session, lock_wait_timeout):
                stmt = sa.select(cls._Table).with_for_update()
                for clause in where_clauses:
                    stmt = stmt.where(clause)
                result = session.execute(stmt)
                return result.scalar_one_or_none()
        except SQLAlchemyOperationalError as e:
            error_msg = str(e.orig) if hasattr(e, "orig") else str(e)
            if "Lock wait timeout exceeded" in error_msg or "1205" in error_msg:
                raise DBRetryableError(f"{PESSIMISTIC_LOCK_ERROR_MSG_TRAIT}-条件锁等待超时: {error_msg}") from e
            raise

    @classmethod
    def iter_record_dtos(
        cls,
        session: Session,
        *,
        where_clauses: list[ColumnExpressionArgument[bool]] | None = None,
        with_deleted: bool = False,
        batch_size: int = 500,
    ) -> Generator[DTOModelT, None, None]:
        for entity in cls._iter_records(
            session,
            cls._Table,
            where_clauses=where_clauses,
            with_deleted=with_deleted,
            batch_size=batch_size,
            pk_attr=cls._pk_attr,
        ):
            yield cls._DTO.model_validate(entity)


class SyncRawDAL:
    """原始数据访问层 (同步版)."""

    @classmethod
    def execute_sql(
        cls,
        session: Session,
        sql: str | sa.TextClause,
        params: _CoreAnyExecuteParams | None = None,
    ) -> sa.Result[Any]:
        if params is None:
            params = {}

        stmt = sql if isinstance(sql, sa.TextClause) else sa.text(sql)
        return session.execute(stmt, params)


class SyncWriteDAL(
    SyncRawDAL,
    SyncRawReadDAL,
    AbstractSyncWriteDAL[Session, SyncSQLATableT, DTOModelT, CUModelT, int],
    Generic[SyncSQLATableT, DTOModelT, CUModelT],
):
    """写入数据访问层基类 (同步版)."""

    _Table: ClassVar[type[SyncSQLATableT]]  # pyright: ignore[reportGeneralTypeIssues]
    _DTO: ClassVar[type[DTOModelT]]  # pyright: ignore[reportGeneralTypeIssues]
    _CU: ClassVar[type[CUModelT]]  # pyright: ignore[reportGeneralTypeIssues]

    @classmethod
    def create(
        cls,
        session: Session,
        cu: CUModelT,
        need_refresh: bool = True,
    ) -> SyncSQLATableT:
        if session.info.get(READONLY_SESSION_FLAG):
            raise TypeError("当前会话被标记为只读, 不允许执行写入操作")
        entity = cu.to_orm_model()
        session.add(entity)
        session.flush()
        if need_refresh:
            session.refresh(entity)
        return cast("SyncSQLATableT", entity)

    @classmethod
    def ret_dto_after_create(
        cls,
        session: Session,
        cu: CUModelT,
        need_refresh: bool = True,
    ) -> DTOModelT:
        entity = cls.create(session, cu, need_refresh)
        return cls._DTO.model_validate(entity)

    @classmethod
    def update_only_set_by_id(
        cls,
        session: Session,
        entity_id: Any,
        cu: CUModelT,
        need_refresh: bool = False,
        *,
        none_policy: NonePolicy = "allow",
    ) -> SyncSQLATableT | None:
        """仅更新 CU 中已设置 (非 unset) 的字段.

        ``none_policy`` 控制显式传入的 ``None`` 如何处理, 详见 ``NonePolicy``:

        - ``allow`` (默认): 写入 SQL ``NULL``, 与 0.7.0 及更早版本行为一致
        - ``ignore``: 跳过 ``None``, 保留库中原值 — 迁移全字段 CU 时推荐显式传入
        - ``forbid``: 遇到 ``None`` 抛 ``ValueError``
        """
        if session.info.get(READONLY_SESSION_FLAG):
            raise TypeError("当前会话被标记为只读, 不允许执行写入操作")
        entity = session.get(cls._Table, entity_id)
        if not entity:
            return None

        update_exclude = type(cu).resolve_cu_config()["update_exclude"]
        update_data = cu.model_dump(exclude_unset=True, exclude=update_exclude)
        for key, value in update_data.items():
            if not _apply_none_policy(key, value, none_policy=none_policy):
                continue
            if hasattr(entity, key):
                setattr(entity, key, value)

        session.flush()
        if need_refresh:
            session.refresh(entity)
        return entity

    @classmethod
    def ret_dto_after_update_by_id(
        cls,
        session: Session,
        entity_id: Any,
        cu: CUModelT,
        need_refresh: bool = True,
        *,
        none_policy: NonePolicy = "allow",
    ) -> DTOModelT | None:
        entity = cls.update_only_set_by_id(session, entity_id, cu, need_refresh, none_policy=none_policy)
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
    def update_full_by_id(
        cls,
        session: Session,
        entity_id: Any,
        cu: CUModelT,
        *,
        need_refresh: bool = False,
        strict_missing: bool = True,
    ) -> SyncSQLATableT | None:
        if session.info.get(READONLY_SESSION_FLAG):
            raise TypeError("当前会话被标记为只读, 不允许执行写入操作")
        entity = session.get(cls._Table, entity_id)
        if not entity:
            return None
        update_exclude = type(cu).resolve_cu_config()["update_exclude"]
        update_data: dict[str, Any] = cu.model_dump(exclude=update_exclude)
        if strict_missing:
            declared_fields = set(cu.__class__.model_fields.keys()) - set(update_exclude)
            missing_declared = [k for k in declared_fields if k not in update_data]
            if missing_declared:
                raise ValueError(f"缺少必须字段: {missing_declared}")
        for key, value in update_data.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
        session.flush()
        if need_refresh:
            session.refresh(entity)
        return entity

    @classmethod
    def update_partial_by_id(
        cls,
        session: Session,
        entity_id: Any,
        cu: CUModelT,
        *,
        need_refresh: bool = False,
        fields: set[InstrumentedAttribute[Any]] | set[sa.Column[Any]] | None = None,
        none_policy: Literal["ignore", "allow", "forbid"] = "ignore",
        none_policy_overrides: dict[InstrumentedAttribute[Any] | sa.Column[Any], Literal["ignore", "allow", "forbid"]] | None = None,
        strict: bool = False,
    ) -> SyncSQLATableT | None:
        if session.info.get(READONLY_SESSION_FLAG):
            raise TypeError("当前会话被标记为只读, 不允许执行写入操作")
        entity = session.get(cls._Table, entity_id)
        if not entity:
            return None
        update_exclude = type(cu).resolve_cu_config()["update_exclude"]
        update_data: dict[str, Any] = cu.model_dump(exclude_unset=True, exclude=update_exclude)
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
        session.flush()
        if need_refresh:
            session.refresh(entity)
        return entity

    @classmethod
    def delete_by_id(
        cls,
        session: Session,
        entity_id: Any,
    ) -> bool:
        if session.info.get(READONLY_SESSION_FLAG):
            raise TypeError("当前会话被标记为只读, 不允许执行写入操作")
        entity = session.get(cls._Table, entity_id)
        if not entity:
            return False

        session.delete(entity)
        session.flush()
        return True

    @classmethod
    def iter_records(
        cls,
        session: Session,
        *,
        where_clauses: list[ColumnExpressionArgument[bool]] | None = None,
        with_deleted: bool = False,
        batch_size: int = 500,
    ) -> Generator[SyncSQLATableT, None, None]:
        yield from cls._iter_records(
            session,
            cls._Table,
            where_clauses=where_clauses,
            with_deleted=with_deleted,
            batch_size=batch_size,
            pk_attr=cls._pk_attr,
        )

    @classmethod
    def batch_update_by_conditions(
        cls,
        session: Session,
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
        result = session.execute(stmt)
        session.flush()
        return result.rowcount  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]

    @classmethod
    def batch_update_by_ids(
        cls,
        session: Session,
        *,
        entity_ids: set[Any] | list[Any],
        update_data: dict[InstrumentedAttribute[Any], Any] | dict[sa.Column[Any], Any],
    ) -> int:
        filtered_ids = filtered_in_sql_values(entity_ids)
        if not filtered_ids:
            return 0
        return cls.batch_update_by_conditions(
            session,
            whereclause=[cls._pk_column().in_(filtered_ids)],
            update_data=update_data,
        )

    @classmethod
    def update_only_set_with_optimistic_lock(
        cls,
        session: Session,
        entity_id: Any,
        cu: CUModelT,
        *,
        expected_version: int,
        need_refresh: bool = False,
        version_field: str = "version",
    ) -> SyncSQLATableT | None:
        if session.info.get(READONLY_SESSION_FLAG):
            raise TypeError("当前会话被标记为只读, 不允许执行写入操作")
        if not hasattr(cls._Table, version_field):
            raise AttributeError(f"表 {cls._Table.__name__} 不包含 {version_field} 字段,无法使用乐观锁")
        pk_col = cls._pk_column()
        exclude_fields = type(cu).resolve_cu_config()["update_exclude"] | {version_field}
        update_data = cu.model_dump(exclude_unset=True, exclude=exclude_fields)
        if not update_data:
            return session.get(cls._Table, entity_id)
        set_values: dict[str, Any] = {key: value for key, value in update_data.items() if hasattr(cls._Table, key)}
        version_field_value = getattr(cls._Table, version_field)
        set_values[version_field] = version_field_value + 1
        stmt = sa.update(cls._Table).where(pk_col == entity_id).where(version_field_value == expected_version).values(**set_values)
        result = session.execute(stmt)
        session.flush()
        if result.rowcount > 0:  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
            entity = session.get(cls._Table, entity_id)
            if need_refresh and entity:
                session.refresh(entity)
            return entity
        raise DBRetryableError(f"{OPTIMISTIC_LOCK_ERROR_MSG_TRAIT}-版本号不匹配({entity_id=}, {expected_version=})")


class SyncXDALOp(SyncRawReadDAL, SyncRawDAL):
    """扩展数据访问操作类 (同步版)."""


class SyncBaseDAL(SyncReadDAL[SyncSQLATableT, DTOModelT], SyncWriteDAL[SyncSQLATableT, DTOModelT, CUModelT]):
    """基础数据访问层 (同步版)."""


class ReadOnlySyncBaseDAL(SyncReadDAL[SyncSQLATableT, ReadOnlyDTOModelT]):
    """只读数据访问层基类 (同步版)."""

    @classmethod
    def _get_dto_fields(cls, dto_class: type[BaseModelT]) -> list[str]:
        return list(dto_class.model_fields.keys())


__all__ = (
    "BasicSyncBaseTable",
    "ReadOnlySyncBaseDAL",
    "ReadOnlySyncBaseTable",
    "SyncBaseDAL",
    "SyncRawDAL",
    "SyncRawReadDAL",
    "SyncReadDAL",
    "SyncSQLATableT",
    "SyncSqlATableBase",
    "SyncWriteDAL",
    "SyncXDALOp",
    "sync_temp_set_lock_wait_timeout",
    "sync_with_retry",
)
