"""共享常量、工具函数、Pydantic 模型、ORM 混入类和事件监听器.

本模块内容 **同步/异步无关**, 被 ``_async`` 和 ``_sync`` 子模块共同导入.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar, Final, Generic, Literal, TypeVar, cast

import sqlalchemy as sa
from lush_dal_protocol.dto import EXTEND_TABLE_CU_CONFIG as EXTEND_TABLE_CU_CONFIG  # noqa: PLC0414
from lush_dal_protocol.dto import BaseCU as _ProtocolBaseCU
from lush_dal_protocol.dto import BaseCUConfigDict as BaseCUConfigDict  # noqa: PLC0414
from lush_dal_protocol.dto import BaseDTO as _ProtocolBaseDTO
from lush_dal_protocol.dto import CUModelT as CUModelT  # noqa: PLC0414
from lush_dal_protocol.dto import DTOModelT as DTOModelT  # noqa: PLC0414
from lush_dal_protocol.dto import pk_field_cu_config as pk_field_cu_config  # noqa: PLC0414
from lush_dal_protocol.errors import (
    OPTIMISTIC_LOCK_ERROR_MSG_TRAIT,
    PESSIMISTIC_LOCK_ERROR_MSG_TRAIT,
    DBRetryableError,
)
from lush_dal_protocol.utils import (
    DEFAULT_RETRY_CONFIG,
    RetryConfig,
    escape_like,
    filtered_in_sql_values,
)
from pydantic import BaseModel, ConfigDict
from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError as SQLAlchemyOperationalError
from sqlalchemy.orm import InstrumentedAttribute, Mapped, ORMExecuteState, mapped_column, with_loader_criteria
from sqlalchemy.orm import Session as SyncSession

READONLY_SESSION_FLAG: Final[str] = "__lush_sqlalchemyx__readonly_session__"

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")
V = TypeVar("V")
BaseModelT = TypeVar("BaseModelT", bound=BaseModel)

# 隐含约束: SQLATableT 应为 SQLAlchemy DeclarativeBase 子类 (含 Flask-SQLAlchemy db.Model).
# 不设 bound 是因为 Flask-SQLAlchemy 的 db.Model 运行时继承 DeclarativeBase,
# 但静态类型系统看不到该链路, bound 会误拦合法下游.
SQLATableT = TypeVar("SQLATableT")


# ---------------------------------------------------------------------------
# Pydantic CU / DTO models
# ---------------------------------------------------------------------------


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

    @classmethod
    def soft_delete_loader_criteria(cls) -> Any:
        """返回 ORM loader criteria 用的「未软删除」谓词.

        默认适用于 ``is_delete == 0`` 整型标记列.
        自定义列类型 (如 ``deleted_at``) 的子类应覆写此方法.
        """
        col_name = getattr(cls, "__soft_delete_column__", "is_delete")
        if not hasattr(cls, col_name):
            return sa.true()
        col = getattr(cls, col_name)
        return col == 0


class FieldIsDeleteSoftDeleteTableMixin(SoftDeleteTableMixin):
    """标准软删除混入类 — 提供 ``is_delete: Mapped[int]`` 列.

    等价旧版 ``SoftDeleteTableMixin``，仅需 rename.
    """

    is_delete: Mapped[int] = mapped_column(
        sa.SmallInteger, default=0, comment="逻辑删除"
    )  # NOTE(@l8ng): 可以优化, 比如给个配置配置mysql可以用tinyint, 现在用 smallint 是因为基本主流数据库都支持


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
                lambda cls: cls.soft_delete_loader_criteria(),
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


def resolve_pk_column(table: type[Any], pk_attr: str = "id") -> InstrumentedAttribute[Any]:
    """解析表上的主键 ``InstrumentedAttribute``.

    Args:
        table: ORM 表类.
        pk_attr: 主键 Python 属性名, 默认 ``"id"``.

    Raises:
        AttributeError: 表上不存在该属性, 或不是 ORM 列.
    """
    col = getattr(table, pk_attr, None)
    if not isinstance(col, InstrumentedAttribute):
        table_name = getattr(table, "__name__", str(table))
        raise AttributeError(f"表 {table_name} 不包含主键字段 {pk_attr!r}, 无法用于按主键操作")
    return cast("InstrumentedAttribute[Any]", col)


def _table_pk_attr_names(table: type[Any]) -> frozenset[str] | None:
    """返回 mapper 主键对应的 Python 属性名; 不可 introspect 时返回 ``None``."""
    try:
        mapper = sa.inspect(table)
    except (sa.exc.NoInspectionAvailable, TypeError):
        return None
    if mapper is None:
        return None
    try:
        pk_cols = mapper.primary_key
    except (AttributeError, TypeError):
        return None
    if not pk_cols:
        return frozenset()
    names: set[str] = set()
    for col in pk_cols:
        name = _pk_attr_name_from_mapper_column(mapper, col)
        if name is not None:
            names.add(name)
    return frozenset(names)


def _pk_attr_name_from_mapper_column(mapper: Any, col: Any) -> str | None:
    """从 mapper 列解析 Python 属性名."""
    try:
        return str(mapper.get_property_by_column(col).key)
    except (AttributeError, KeyError, ValueError):
        key = getattr(col, "key", None) or getattr(col, "name", None)
        return str(key) if key is not None else None


def validate_orm_dal_pk_config(dal_cls: type[Any]) -> None:
    """校验 ORM DAL 的 ``_pk_attr`` 与 Table / CU 配置一致.

    在具体 DAL 子类创建时调用. 无 ``_Table`` 的中间基类、以及不可
    ``sa.inspect`` 的测试 double / 非映射类直接跳过.

    - ``_Table`` 上必须存在 ``_pk_attr`` 对应 ORM 列
    - 若表已声明主键, ``_pk_attr`` 必须属于 mapper 主键属性
    - 若绑定 ``_CU``, 其 ``update_exclude`` 必须包含 ``_pk_attr``
      (避免默认仍按 ``\"id\"`` 排除而自定义主键漏配)

    Raises:
        TypeError: 配置不一致.
    """
    table = getattr(dal_cls, "_Table", None)
    if not isinstance(table, type):
        return
    if getattr(table, "__abstract__", False) and getattr(table, "__tablename__", None) is None:
        return

    # 非 SQLAlchemy mapped class (单元测试 double 等) 不强制.
    pk_names = _table_pk_attr_names(table)
    if pk_names is None:
        return

    pk_attr = getattr(dal_cls, "_pk_attr", "id")
    if not isinstance(pk_attr, str) or not pk_attr:
        raise TypeError(f"{dal_cls.__name__}: _pk_attr 必须为非空 str, 当前为 {pk_attr!r}")

    try:
        resolve_pk_column(table, pk_attr)
    except AttributeError as e:
        raise TypeError(str(e)) from e

    if pk_names and pk_attr not in pk_names:
        raise TypeError(
            f"{dal_cls.__name__}: _pk_attr={pk_attr!r} 不在表 {table.__name__} 的主键属性 {sorted(pk_names)} 中; "
            f"请将 _pk_attr 改为表主键属性名"
        )

    cu = getattr(dal_cls, "_CU", None)
    if not isinstance(cu, type):
        return
    resolve = getattr(cu, "resolve_cu_config", None)
    if not callable(resolve):
        return
    cfg = resolve()
    if not isinstance(cfg, dict):
        return
    update_exclude = cfg.get("update_exclude")
    if update_exclude is None:
        return
    if pk_attr not in update_exclude:
        raise TypeError(
            f"{dal_cls.__name__}: _pk_attr={pk_attr!r} 但 {cu.__name__}.cu_config "
            f"update_exclude={set(update_exclude)!r} 未包含该主键; "
            f"请使用 pk_field_cu_config({pk_attr!r}) 与 DAL._pk_attr 成对配置"
        )


NonePolicy = Literal["ignore", "allow", "forbid"]
"""更新 API 中对 **显式** ``None`` 字段的处理策略.

用于 ``update_only_set_by_id`` / ``update_partial_by_id`` 等写入路径.
注意: Pydantic ``model_dump(exclude_unset=True)`` 仍会包含「已设置」的 ``None``
(例如迁移时用全字段 CU 校验后缺省列变成 ``None``), 与「未传字段」不同.

- ``ignore``: 跳过值为 ``None`` 的字段, 不写入 UPDATE, 保留库中原值
  (迁移全字段 CU 时推荐在 ``update_only_set_by_id`` 显式传入)
- ``allow``: 将字段置为 SQL ``NULL`` (``update_only_set_by_id`` 的默认策略,
  与 0.7.0 及更早版本行为一致)
- ``forbid``: 遇到显式 ``None`` 立即抛 ``ValueError``

``setattr(entity, key, None)`` 与 ``entity.key = None`` 在 SQLAlchemy ORM 上等价,
都会把属性标 dirty 并在 flush 时发出 ``SET col = NULL``; 库侧防护点在「是否把
该键加入 dirty set」, 而非赋值语法.
"""


def _apply_none_policy(
    key: str,
    value: Any,
    *,
    none_policy: NonePolicy,
) -> bool:
    """根据 ``none_policy`` 决定是否将字段写入更新.

    Returns:
        ``True`` 表示应 ``setattr`` 该字段; ``False`` 表示跳过 (``ignore``).

    Raises:
        ValueError: ``none_policy="forbid"`` 且 ``value is None``.
    """
    if value is not None:
        return True
    if none_policy == "ignore":
        return False
    if none_policy == "forbid":
        raise ValueError(f"字段不允许置空: {key}")
    # allow
    return True


# Re-export OperationalError so downstream modules don't need a separate import.
SQLAlchemyOperationalError = SQLAlchemyOperationalError

__all__ = (
    "DEFAULT_RETRY_CONFIG",
    "EXTEND_TABLE_CU_CONFIG",
    "OPTIMISTIC_LOCK_ERROR_MSG_TRAIT",
    "PESSIMISTIC_LOCK_ERROR_MSG_TRAIT",
    "READONLY_SESSION_FLAG",
    "_LOGGER",
    "BaseCU",
    "BaseCUConfigDict",
    "BaseDTO",
    "BaseModelT",
    "CUModelT",
    "DBRetryableError",
    "DTOModelT",
    "FieldMixin",
    "NonePolicy",
    "ReadOnlyMixin",
    "RetryConfig",
    "SQLATableT",
    "SQLAlchemyOperationalError",
    "SoftDeleteTableMixin",
    "T",
    "V",
    "_apply_none_policy",
    "_ensure_strict_fields",
    "FieldIsDeleteSoftDeleteTableMixin",
    "escape_like",
    "filtered_in_sql_values",
    "is_soft_delete_hooks_registered",
    "pk_field_cu_config",
    "register_soft_delete_hooks",
    "resolve_pk_column",
    "setup_dal_hooks",
    "unregister_soft_delete_hooks",
    "validate_orm_dal_pk_config",
)
