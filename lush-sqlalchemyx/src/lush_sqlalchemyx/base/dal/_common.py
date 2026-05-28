"""共享常量、工具函数、Pydantic 模型、ORM 混入类和事件监听器.

本模块内容 **同步/异步无关**, 被 ``_async`` 和 ``_sync`` 子模块共同导入.
"""

from __future__ import annotations

import datetime
import logging
import random
import warnings
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, ClassVar, Final, Generic, TypeVar, cast

import sqlalchemy as sa
from lush_dal_protocol.dto import BaseCU as _ProtocolBaseCU
from lush_dal_protocol.dto import BaseDTO as _ProtocolBaseDTO
from lush_dal_protocol.dto import CUModelT as CUModelT  # noqa: PLC0414
from lush_dal_protocol.dto import DTOModelT as DTOModelT  # noqa: PLC0414
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError as SQLAlchemyOperationalError
from sqlalchemy.orm import Mapped, ORMExecuteState, mapped_column, with_loader_criteria
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

# 隐含约束: SQLATableT 应为 SQLAlchemy DeclarativeBase 子类 (含 Flask-SQLAlchemy db.Model).
# 不设 bound 是因为 Flask-SQLAlchemy 的 db.Model 运行时继承 DeclarativeBase,
# 但静态类型系统看不到该链路, bound 会误拦合法下游.
SQLATableT = TypeVar("SQLATableT")


class BaseCU(_ProtocolBaseCU[SQLATableT]):
    """SQLAlchemy 专用 CU 基类, 继承 ``lush_dal_protocol.dto.BaseCU``."""

    model_config = ConfigDict(str_strip_whitespace=True)

    _Table: ClassVar[type[SQLATableT]]  # pyright: ignore[reportGeneralTypeIssues,reportIncompatibleVariableOverride]

    def to_sqla_model(self) -> SQLATableT:
        """``to_orm_model`` 的 SQLAlchemy 兼容别名."""
        return self.to_orm_model()


class BaseDTO(_ProtocolBaseDTO[CUModelT]):
    """SQLAlchemy 专用 DTO 基类, 继承 ``lush_dal_protocol.dto.BaseDTO``."""

    model_config = ConfigDict(from_attributes=True)


class StdBaseCU(BaseCU[SQLATableT]):
    """标准 CU 基类: 包含创建人/修改人等标准字段.

    .. deprecated::
        此类预设了特定业务字段, 下游应自行继承 ``BaseCU`` 定义所需字段.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        warnings.warn(
            f"{cls.__name__} 继承了已废弃的 StdBaseCU, 请改为直接继承 BaseCU 并自行定义所需字段",
            DeprecationWarning,
            stacklevel=2,
        )

    create_operator_id: int = 0
    update_operator_id: int | None = None


class StdBaseDTO(BaseDTO[CUModelT]):
    """标准 DTO 基类: 包含 id/时间戳/操作人等标准字段.

    .. deprecated::
        此类预设了特定业务字段, 下游应自行继承 ``BaseDTO`` 定义所需字段.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        warnings.warn(
            f"{cls.__name__} 继承了已废弃的 StdBaseDTO, 请改为直接继承 BaseDTO 并自行定义所需字段",
            DeprecationWarning,
            stacklevel=2,
        )

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
    """软删除表标记混入类 — 不强制任何列名或类型.

    子类必须提供软删除列并覆写 ``is_soft_deleted`` property.
    快捷方式: 继承 ``FieldIsDeleteSoftDeleteTableMixin`` 获得标准 ``is_delete`` 列.

    自定义示例::

        class MyTable(Base, SoftDeleteTableMixin):
            __soft_delete_column__ = "deleted_at"

            deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True, default=None)

            @property
            def is_soft_deleted(self) -> bool:
                return self.deleted_at is not None

            def soft_delete(self) -> None:
                from datetime import datetime, timezone

                self.deleted_at = datetime.now(timezone.utc)
    """

    __soft_delete_column__: ClassVar[str] = "is_delete"

    def soft_delete(self) -> None:
        """标记为软删除."""
        setattr(self, self.__soft_delete_column__, 1)

    def soft_undelete(self) -> None:
        """恢复软删除."""
        setattr(self, self.__soft_delete_column__, 0)

    @property
    def is_soft_deleted(self) -> bool:
        """实体是否已被软删除（默认检查 ``is_delete != 0``，子类可覆写）."""
        return bool(getattr(self, self.__soft_delete_column__))


class FieldIsDeleteSoftDeleteTableMixin(SoftDeleteTableMixin):
    """标准软删除混入类 — 提供 ``is_delete: Mapped[int]`` 列.

    等价旧版 ``SoftDeleteTableMixin``，仅需 rename.
    """

    is_delete: Mapped[int] = mapped_column(sa.Integer, default=0, comment="逻辑删除")


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
# Soft-delete hook management API (explicit register/unregister/check)
# ---------------------------------------------------------------------------


def register_soft_delete_hooks() -> None:
    """显式注册软删除 Session 事件监听器（幂等）。

    在以下场景需要显式调用:
    - 多进程 worker 子进程（import 可能未触发）
    - 测试中自建 Session、未走应用启动链
    - FastAPI lifespan / Flask app factory 显式初始化
    """
    if not sa_event.contains(SyncSession, "before_flush", __receive_before_flush):
        sa_event.listen(SyncSession, "before_flush", __receive_before_flush, insert=True)
    if not sa_event.contains(SyncSession, "do_orm_execute", __add_filtering_criteria):
        sa_event.listen(SyncSession, "do_orm_execute", __add_filtering_criteria, insert=True)


def unregister_soft_delete_hooks() -> None:
    """注销软删除 Session 事件监听器（幂等）。"""
    if sa_event.contains(SyncSession, "before_flush", __receive_before_flush):
        sa_event.remove(SyncSession, "before_flush", __receive_before_flush)
    if sa_event.contains(SyncSession, "do_orm_execute", __add_filtering_criteria):
        sa_event.remove(SyncSession, "do_orm_execute", __add_filtering_criteria)


def is_soft_delete_hooks_registered() -> bool:
    """检查软删除钩子是否已注册。"""
    return sa_event.contains(SyncSession, "before_flush", __receive_before_flush) and sa_event.contains(
        SyncSession, "do_orm_execute", __add_filtering_criteria
    )


def setup_dal_hooks() -> None:
    """注册所有必要的 Session 事件监听器（幂等）。

    在应用生命周期开始时**调用一次**即可，无需关注具体注册了哪些钩子。
    涵盖：软删除拦截、软删除查询过滤、只读保护。

    **时序说明**: 模型类的定义（继承 SoftDeleteTableMixin / ReadOnlyMixin）
    可以在调用 setup_dal_hooks 之前或之后 — 均不影响钩子生效。
    因为钩子注册在 SyncSession 上，在 flush/query 时通过 isinstance 和
    with_loader_criteria 动态评估，不依赖模型类在注册时刻的状态。

    FastAPI 示例::

        @asynccontextmanager
        async def lifespan(app):
            setup_dal_hooks()
            yield

    Flask 示例::

        def create_app():
            app = Flask(__name__)
            setup_dal_hooks()
            return app
    """
    register_soft_delete_hooks()
    if not sa_event.contains(SyncSession, "before_flush", __prevent_readonly_write):
        sa_event.listen(SyncSession, "before_flush", __prevent_readonly_write, insert=True)


# ---------------------------------------------------------------------------
# Session event listeners (registered on SyncSession — works for both sync
# and async since AsyncSession delegates to a SyncSession internally).
#
# 不再使用 @sa_event.listens_for 装饰器在 import 时自动注册。
# 改为通过 setup_dal_hooks() / register_soft_delete_hooks() 显式注册。
# 这样做的原因: 让注册时机清晰可预测, 避免用户对"何时调用 setup_dal_hooks"
# 产生困惑。在 Flask/FastAPI 集成中 auto-call 保证开箱即用。
#
# 模型类定义在 setup_dal_hooks 之前或之后均不影响钩子生效 —
# isinstance 和 with_loader_criteria 在 flush/query 时动态评估。
# ---------------------------------------------------------------------------


def __receive_before_flush(session: SyncSession, flush_context: Any, instances: Any) -> None:  # noqa: ARG001 # pyright: ignore[reportUnusedFunction, reportUnusedParameter]
    for instance in session.deleted:
        if isinstance(instance, SoftDeleteTableMixin):
            instance.soft_delete()
            session.add(instance)


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
                lambda cls: getattr(cls, getattr(cls, "__soft_delete_column__", "is_delete"), sa.null()) == 0,
                include_aliases=True,
            )
        )


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
    "FieldIsDeleteSoftDeleteTableMixin",
    "escape_like",
    "filtered_in_sql_values",
    "is_soft_delete_hooks_registered",
    "register_soft_delete_hooks",
    "setup_dal_hooks",
    "unregister_soft_delete_hooks",
)
