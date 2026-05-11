"""共享常量、工具函数、Pydantic 模型、ORM 混入类和事件监听器.

本模块内容 **同步/异步无关**, 被 ``_async`` 和 ``_sync`` 子模块共同导入.
"""

from __future__ import annotations

import datetime
import logging
import random
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, ClassVar, Final, Generic, TypeVar, cast

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError as SQLAlchemyOperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, ORMExecuteState, mapped_column, with_loader_criteria
from sqlalchemy.orm import Session as SyncSession

READONLY_SESSION_FLAG: Final[str] = "__lush_sqlalchemyx__readonly_session__"

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")
V = TypeVar("V")
BaseModelT = TypeVar("BaseModelT", bound=BaseModel)

OPTIMISTIC_LOCK_ERROR_MSG_TRAIT: Final[str] = "乐观锁更新失败"
PESSIMISTIC_LOCK_ERROR_MSG_TRAIT: Final[str] = "悲观锁获取失败"


# ---------------------------------------------------------------------------
# Pure utility functions
# ---------------------------------------------------------------------------


def filtered_in_sql_values(
    values: Iterable[V] | None,
    target_type_as: Callable[[V], T] = lambda x: x,
) -> list[T]:
    if not values:
        return []

    items: list[T] = []
    seen = set[T]()

    for item in values:
        if item is None or item == "":
            continue
        try:
            converted_value = target_type_as(item)
            if converted_value not in seen:
                seen.add(converted_value)
                items.append(converted_value)
        except (ValueError, TypeError):
            continue

    return items


def escape_like(value: str, escape_char: str = "\\") -> tuple[str, str]:
    """转义用于 SQL LIKE 的特殊字符并返回转义后的值和转义字符."""
    v = value.replace(escape_char, escape_char + escape_char)
    v = v.replace("%", escape_char + "%").replace("_", escape_char + "_")
    return v, escape_char


# ---------------------------------------------------------------------------
# Retryable error & retry config
# ---------------------------------------------------------------------------


class DBRetryableError(Exception):
    """数据库可重试异常

    表示一个由于并发冲突导致的、可以通过重试解决的数据库操作异常.
    这类异常不是错误,而是正常的并发控制机制,应该被捕获并重试.
    """

    def __init__(self, message: str = "数据库操作冲突,需要重试") -> None:
        super().__init__(message)
        self.message = message

    @property
    def is_pessimistic_lock_retry_error(self) -> bool:
        return PESSIMISTIC_LOCK_ERROR_MSG_TRAIT in self.message

    @property
    def is_optimistic_lock_retry_error(self) -> bool:
        return OPTIMISTIC_LOCK_ERROR_MSG_TRAIT in self.message


@dataclass
class RetryConfig:
    """重试配置"""

    max_attempts: int = 3
    initial_delay: float = 0.1
    max_delay: float = 2.0
    exponential_base: float = 2.0
    jitter: bool = True

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts必须>=1, 当前值: {self.max_attempts}")
        if self.initial_delay < 0:
            raise ValueError(f"initial_delay必须>=0, 当前值: {self.initial_delay}")
        if self.max_delay < self.initial_delay:
            raise ValueError(f"max_delay({self.max_delay})必须>=initial_delay({self.initial_delay})")
        if self.exponential_base <= 1:
            raise ValueError(f"exponential_base必须>1, 当前值: {self.exponential_base}")

    def calculate_delay(self, attempt: int) -> float:
        if attempt <= 0:
            return 0.0

        delay = self.initial_delay * (self.exponential_base ** (attempt - 1))
        delay = min(delay, self.max_delay)

        if self.jitter and delay > 0:
            jitter_range = delay * 0.2
            delay = delay + random.uniform(-jitter_range, jitter_range)  # noqa: S311
            delay = max(0, min(delay, self.max_delay))

        return delay


DEFAULT_RETRY_CONFIG = RetryConfig(max_attempts=3, initial_delay=0.1, max_delay=1.0)


# ---------------------------------------------------------------------------
# Pydantic CU / DTO models
# ---------------------------------------------------------------------------

SQLATableT = TypeVar("SQLATableT", bound=DeclarativeBase)


class BaseCU(BaseModel, Generic[SQLATableT]):
    """创建/更新模型基类."""

    model_config = ConfigDict(str_strip_whitespace=True)

    _Table: ClassVar[type[SQLATableT]]  # pyright: ignore[reportGeneralTypeIssues]

    def to_sqla_model(self) -> SQLATableT:
        model_data = self.model_dump(exclude_unset=True, exclude={"id"})
        return self._Table(**model_data)


CUModelT = TypeVar("CUModelT", bound=BaseCU[Any])


class BaseDTO(BaseModel, Generic[CUModelT]):
    """数据传输对象基类."""

    model_config = ConfigDict(from_attributes=True)

    _CU: ClassVar[type[CUModelT]]  # pyright: ignore[reportGeneralTypeIssues]

    def to_cu(self) -> CUModelT:
        return self._CU.model_validate(self)


DTOModelT = TypeVar("DTOModelT", bound=BaseDTO[Any] | BaseModel)


class StdBaseCU(BaseCU[SQLATableT]):
    """标准 CU 基类:包含标准字段的 CU 类."""

    create_operator_id: int = 0
    update_operator_id: int | None = None


class StdBaseDTO(BaseDTO[CUModelT]):
    """标准 DTO 基类:包含标准字段的 DTO 类."""

    id: int = Field(..., description="ID")
    create_datetime: datetime.datetime = Field(..., description="创建时间")
    create_operator_id: int = Field(..., description="创建人")
    update_datetime: datetime.datetime | None = Field(None, description="修改时间")
    update_operator_id: int | None = Field(None, description="修改人")

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# ORM Mixins
# ---------------------------------------------------------------------------


class SoftDeleteTableMixin:
    """软删除表混入类."""

    is_delete: Mapped[int] = mapped_column(sa.Integer, default=0, comment="逻辑删除")

    def delete(self, is_delete: int = 1) -> None:
        self.is_delete = is_delete

    def undelete(self) -> None:
        self.is_delete = 0


class ReadOnlyMixin:
    """只读表标记混入类 - 基于 SQLAlchemy 事件监听系统的只读保护."""


class FieldMixin:
    """字段混入类."""

    class DataJsonBytes(Generic[BaseModelT]):
        """为 bytes 类型的 JSON 列提供简单直观的读写接口."""

        _DATA_JSON_FIELD: ClassVar[str] = "data_json"
        _DATA_JSON: ClassVar[type[BaseModelT]]  # pyright: ignore[reportGeneralTypeIssues]

        @property
        def must_x_data_json(self) -> BaseModelT:
            return cast("BaseModelT", self.x_data_json)

        @property
        def x_data_json(self) -> BaseModelT | None:
            if not hasattr(self, "_DATA_JSON"):
                return None

            raw = getattr(self, self._DATA_JSON_FIELD, None)
            if not raw:
                return self._DATA_JSON()  # type: ignore[call-arg]

            if isinstance(raw, bytes):
                text = raw.decode()
            else:
                text = str(raw)

            return self._DATA_JSON.model_validate_json(text)

        @x_data_json.setter
        def x_data_json(self, value: BaseModelT | None) -> None:
            if value is None:
                setattr(self, self._DATA_JSON_FIELD, b"{}")
                return

            if isinstance(value, BaseModel):
                setattr(self, self._DATA_JSON_FIELD, value.model_dump_json().encode())
                return


# ---------------------------------------------------------------------------
# Session event listeners (registered on SyncSession — works for both sync
# and async since AsyncSession delegates to a SyncSession internally)
# ---------------------------------------------------------------------------


@sa_event.listens_for(SyncSession, "before_flush")
def __receive_before_flush(session: SyncSession, flush_context: Any, instances: Any) -> None:  # noqa: ARG001 # pyright: ignore[reportUnusedFunction, reportUnusedParameter]
    for instance in session.deleted:
        if isinstance(instance, SoftDeleteTableMixin):
            instance.delete()
            session.add(instance)


@sa_event.listens_for(SyncSession, "do_orm_execute")
def __add_filtering_criteria(execute_state: ORMExecuteState) -> None:  # pyright: ignore[reportUnusedFunction]
    if (
        not execute_state.is_column_load
        and not execute_state.is_relationship_load
        and not execute_state.execution_options.get("include_soft_deleted", False)
        and execute_state.statement.is_select
    ):
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                SoftDeleteTableMixin,
                lambda t: t.is_delete == 0,
                include_aliases=True,
            )
        )


@sa_event.listens_for(SyncSession, "before_flush")
def __prevent_readonly_write(session: SyncSession, flush_context: Any, instances: Any) -> None:  # noqa: ARG001 # pyright: ignore[reportUnusedFunction, reportUnusedParameter]
    for obj in session.new.union(session.dirty).union(session.deleted):
        if isinstance(obj, ReadOnlyMixin):
            operation = "创建" if obj in session.new else "更新" if obj in session.dirty else "删除"
            raise TypeError(
                f"不允许对只读模型 '{type(obj).__name__}' 执行 {operation} 操作." + "此表已被标记为只读,请检查业务逻辑是否正确."
            )


# ---------------------------------------------------------------------------
# Shared helpers used by both async & sync DAL _ensure_strict_fields
# ---------------------------------------------------------------------------


def _ensure_strict_fields(
    *,
    provided_keys: set[str],
    allowed_names: set[str] | None,
    strict: bool,
) -> None:
    if not strict or allowed_names is None:
        return
    not_allowed = [k for k in provided_keys if k not in allowed_names]
    if not_allowed:
        raise ValueError(f"出现未允许更新的字段: {not_allowed}")


# Re-export OperationalError so downstream modules don't need a separate import.
SQLAlchemyOperationalError = SQLAlchemyOperationalError

__all__ = (
    "DEFAULT_RETRY_CONFIG",
    "OPTIMISTIC_LOCK_ERROR_MSG_TRAIT",
    "PESSIMISTIC_LOCK_ERROR_MSG_TRAIT",
    "READONLY_SESSION_FLAG",
    "_LOGGER",
    "BaseCU",
    "BaseDTO",
    "BaseModelT",
    "CUModelT",
    "DBRetryableError",
    "DTOModelT",
    "FieldMixin",
    "ReadOnlyMixin",
    "RetryConfig",
    "SQLATableT",
    "SQLAlchemyOperationalError",
    "SoftDeleteTableMixin",
    "StdBaseCU",
    "StdBaseDTO",
    "T",
    "V",
    "_ensure_strict_fields",
    "escape_like",
    "filtered_in_sql_values",
)
