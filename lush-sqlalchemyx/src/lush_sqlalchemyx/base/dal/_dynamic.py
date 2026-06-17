"""无需 ORM Table class 的动态 DAL — 用 TableRef + CU/DTO 直接操作表.
from __future__ import annotations

本模块提供两条路径:

1. **TableRef**: 轻量表引用, 用表名 + 列名映射替代 DeclarativeBase 子类.
   列映射可从 Pydantic DTO 自动推导 (alias 优先于 field_name).

2. **DynamicSyncDAL / DynamicAsyncDAL**: 基于 TableRef 的 CRUD, 走 SQLAlchemy Core.
   支持软删除拦截和只读保护, 与 ORM DAL 行为对齐.

使用场景:
- 已有 schema 的表, 只需 CU/DTO + 表名即可操作
- 不想定义 ORM Table class
- 视图表、外部表、临时表等轻量操作
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, Generic, TypeVar

import sqlalchemy as sa
from lush_dal_protocol import NO_SESSION, NoSession
from lush_dal_protocol.abc.base_composed import BaseAsyncBaseDAL, BaseSyncBaseDAL
from pydantic import AliasChoices, AliasPath, BaseModel
from sqlalchemy import ColumnElement, Result
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.sql import TableClause
from typing_extensions import Self
from typing_extensions import TypeVar as TypeVarExt

DTOModelT = TypeVar("DTOModelT", bound=BaseModel)
CUModelT = TypeVar("CUModelT", bound=BaseModel)
PrimaryKeyT = TypeVarExt("PrimaryKeyT", default=int)


# ---------------------------------------------------------------------------
# 推导函数
# ---------------------------------------------------------------------------


def _resolve_alias(field_info: Any) -> str | None:
    """从 FieldInfo 提取 db 列名 (alias 优先于 validation_alias).

    Returns:
        列名字符串, 字段无任何 alias 时返回 ``None`` (由调用方回退到 field_name).
    """
    if field_info.alias:
        return field_info.alias
    va = field_info.validation_alias
    if isinstance(va, AliasChoices):
        first = va.choices[0]
        return str(first) if isinstance(first, (str, AliasPath)) else None
    if isinstance(va, (str, AliasPath)):
        return str(va)
    return None


def derive_columns_from_dto(dto_class: type[BaseModel]) -> dict[str, str]:
    """从 DTO 推导 column mapping: ``{python_field: db_column}``.

    优先级: ``alias`` > ``validation_alias`` 首个 choice > ``field_name``.

    Args:
        dto_class: Pydantic DTO 模型类.

    Returns:
        ``{python_field_name: db_column_name}`` 字典.
    """
    columns: dict[str, str] = {}
    for field_name, field_info in dto_class.model_fields.items():
        columns[field_name] = _resolve_alias(field_info) or field_name
    return columns


def derive_pk_from_dto(dto_class: type[BaseModel]) -> str:
    """从 DTO 推导主键列名.

    取 ``DTO.fields["id"].alias``, 无 ``"id"`` 字段时抛 ``ValueError``.

    Args:
        dto_class: Pydantic DTO 模型类.

    Returns:
        主键的 db column 名.

    Raises:
        ValueError: DTO 无 ``"id"`` 字段.
    """
    fi = dto_class.model_fields.get("id")
    if fi is None:
        raise ValueError(f"DTO {dto_class.__name__} 没有 'id' 字段, 请手动指定 pk_column")
    return _resolve_alias(fi) or "id"


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DynamicTableConfig:
    """动态表的软删除 / 只读配置.

    Attributes:
        soft_delete_column: 软删除列名, ``None`` 表示不启用软删除.
        soft_delete_value: 软删除时写入的值.
        soft_undelete_value: 恢复时写入的值.
        is_readonly: 只读保护, 拒绝一切写入操作.
    """

    soft_delete_column: str | None = None
    soft_delete_value: Any = 1
    soft_undelete_value: Any = 0
    is_readonly: bool = False


# ---------------------------------------------------------------------------
# TableRef
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TableRef(Generic[PrimaryKeyT]):
    """无 ORM 模型的表引用 — 用表名 + 列名映射替代 DeclarativeBase 子类.

    ``pk_column`` 和 ``columns`` 均可选: 不传时自动从 ``dto`` 推导,
    传入时用户指定的值优先级最高.

    推导优先级::

        pk_column:  用户指定 > DTO.fields["id"].alias > "id"
        columns:    用户指定 > DTO 全量字段 (alias 优先于 field_name)

    类型参数:
        PrimaryKeyT: 主键类型, 默认 ``int``. 非自增主键 (UUID/string) 时显式指定.

    Attributes:
        table_name: 数据库表名.
        pk_column: 主键列名, ``None`` 时自动从 DTO 推导.
        columns: ``{python_field: db_column}`` 映射, ``None`` 时自动从 DTO 推导.
        config: 软删除 / 只读配置.
    """

    table_name: str
    pk_column: str | None = None
    columns: dict[str, str] | None = None
    config: DynamicTableConfig = field(default_factory=DynamicTableConfig)

    _dto_class: type[BaseModel] | None = field(default=None, repr=False, compare=False)  # type: ignore[assignment]

    # ── 构造器 ──────────────────────────────────────────

    @classmethod
    def of(
        cls,
        table_name: str,
        dto: type[BaseModel],
        *,
        pk_column: str | None = None,
        columns: dict[str, str] | None = None,
    ) -> Self:
        """通用构造器 — 自动从 DTO 推导 pk_column 和 columns.

        Args:
            table_name: 数据库表名.
            dto: Pydantic DTO 模型类, 用于推导列映射.
            pk_column: 主键列名, 不传时自动推导.
            columns: 列映射, 不传时自动推导.
        """
        return cls(
            table_name=table_name,
            pk_column=pk_column,
            columns=columns,
            _dto_class=dto,
        )

    @classmethod
    def with_soft_delete(
        cls,
        table_name: str,
        dto: type[BaseModel],
        *,
        pk_column: str | None = None,
        columns: dict[str, str] | None = None,
        soft_delete_column: str = "is_delete",
    ) -> Self:
        """构造带软删除配置的 TableRef.

        Args:
            table_name: 数据库表名.
            dto: Pydantic DTO 模型类.
            pk_column: 主键列名, 不传时自动推导.
            columns: 列映射, 不传时自动推导.
            soft_delete_column: 软删除列名.
        """
        return cls(
            table_name=table_name,
            pk_column=pk_column,
            columns=columns,
            config=DynamicTableConfig(soft_delete_column=soft_delete_column),
            _dto_class=dto,
        )

    @classmethod
    def readonly(
        cls,
        table_name: str,
        dto: type[BaseModel],
        *,
        pk_column: str | None = None,
        columns: dict[str, str] | None = None,
    ) -> Self:
        """构造只读 TableRef.

        Args:
            table_name: 数据库表名.
            dto: Pydantic DTO 模型类.
            pk_column: 主键列名, 不传时自动推导.
            columns: 列映射, 不传时自动推导.
        """
        return cls(
            table_name=table_name,
            pk_column=pk_column,
            columns=columns,
            config=DynamicTableConfig(is_readonly=True),
            _dto_class=dto,
        )

    # ── 推导结果 ────────────────────────────────────────

    @cached_property
    def resolved_pk_column(self) -> str:
        """解析后的主键列名: 用户指定 > DTO 推导."""
        if self.pk_column is not None:
            return self.pk_column
        assert self._dto_class is not None, "未指定 pk_column 时必须传入 dto"  # noqa: S101
        return derive_pk_from_dto(self._dto_class)

    @cached_property
    def resolved_columns(self) -> dict[str, str]:
        """解析后的列映射: 用户指定 > DTO 推导."""
        if self.columns is not None:
            return self.columns
        assert self._dto_class is not None, "未指定 columns 时必须传入 dto"  # noqa: S101
        return derive_columns_from_dto(self._dto_class)

    @cached_property
    def pk_field_name(self) -> str:
        """主键对应的 Python 字段名 (从 ``resolved_columns`` 反查)."""
        pk_col = self.resolved_pk_column
        for py_field, db_col in self.resolved_columns.items():
            if db_col == pk_col:
                return py_field
        # PK 不在 columns 中 (如用户手动指定), 回退到 db column 名
        return pk_col

    # ── Core 构建 ───────────────────────────────────────

    @cached_property
    def sa_table(self) -> TableClause:
        """SQLAlchemy Core table 对象 — 不依赖 ORM."""
        all_cols = set(self.resolved_columns.values())
        # 软删除列可能不在 DTO 字段中, 但必须在 sa_table 中 (UPDATE SET 需要)
        sd_col = self.config.soft_delete_column
        if sd_col is not None:
            all_cols.add(sd_col)
        return sa.table(
            self.table_name,
            *[sa.column(c) for c in all_cols],
        )

    def pk(self) -> sa.ColumnClause[Any]:
        """主键列对象."""
        return sa.column(self.resolved_pk_column)

    # ── 映射 ───────────────────────────────────────────

    def map_to_row_data(self, cu_data: dict[str, Any]) -> dict[str, Any]:
        """CU 字典 → ``{db_column: value}`` 映射 (自动过滤不相关字段)."""
        return {db_col: cu_data[py_field] for py_field, db_col in self.resolved_columns.items() if py_field in cu_data}

    @cached_property
    def _db_col_to_val_key(self) -> dict[str, str]:
        """``{db_column: validation_key}`` 反向映射.

        ``model_validate`` 接受的 key 优先级:
        ``validation_alias`` > ``alias`` > ``field_name``.
        """
        result: dict[str, str] = {}
        assert self._dto_class is not None, "_db_col_to_val_key 需要 dto"  # noqa: S101
        for field_name, field_info in self._dto_class.model_fields.items():
            db_col = self.resolved_columns[field_name]
            va = field_info.validation_alias
            if isinstance(va, AliasChoices):
                val_key = str(va.choices[0])
            elif isinstance(va, (str, AliasPath)):
                val_key = str(va)
            elif field_info.alias:
                val_key = field_info.alias
            else:
                val_key = field_name
            result[db_col] = val_key
        return result

    def map_from_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """``{db_column: value}`` → ``{validation_key: value}``.

        映射到 ``model_validate`` 能识别的 key (alias/validation_alias),
        而非 Python 字段名.
        """
        mapping = self._db_col_to_val_key
        return {mapping.get(k, k): v for k, v in row.items()}

    # ── 守卫 ───────────────────────────────────────────

    def guard_readonly(self, operation: str) -> None:
        """只读守卫 — 只读表拒绝写入操作."""
        if self.config.is_readonly:
            raise TypeError(f"表 '{self.table_name}' 被标记为只读, 不允许执行 {operation} 操作")

    # ── 共享 DAL 逻辑 ──────────────────────────────────

    def apply_select_filter(self, stmt: sa.Select[Any]) -> sa.Select[Any]:
        """为 SELECT 语句注入软删除过滤条件."""
        cfg = self.config
        if cfg.soft_delete_column is not None:
            stmt = stmt.where(sa.column(cfg.soft_delete_column) == cfg.soft_undelete_value)
        return stmt

    def resolve_pk(self, result: Result[Any]) -> PrimaryKeyT | None:
        """从 INSERT 结果获取主键.

        ``sa.table()`` 不知道主键约束, ``inserted_primary_key`` 可能为空,
        用 ``lastrowid`` 作为 fallback (仅适用于整数自增主键).

        非自增主键 (UUID/string) 应由调用方在 CU 中提供,
        ``inserted_primary_key`` 能正确返回.

        Returns:
            主键值, 无法获取时返回 ``None``.
        """
        ipk = getattr(result, "inserted_primary_key", None)
        if ipk and ipk[0] is not None:
            return ipk[0]
        return getattr(result, "lastrowid", None)  # type: ignore[return-value]

    def cu_row_data(self, cu: BaseModel) -> dict[str, Any]:
        """CU 模型 → ``{db_column: value}`` dict (排除 PK 字段)."""
        return self.map_to_row_data(cu.model_dump(exclude_unset=True, exclude={self.pk_field_name}))


# ---------------------------------------------------------------------------
# DynamicSyncDAL
# ---------------------------------------------------------------------------


class DynamicSyncDAL(
    BaseSyncBaseDAL[Session, DTOModelT, CUModelT, PrimaryKeyT],
    Generic[DTOModelT, CUModelT, PrimaryKeyT],
):
    """无需 Table class 的同步动态 DAL.

    用 SQLAlchemy Core 替代 ORM, 提供与 ``SyncBaseDAL`` 对齐的 CRUD API.
    支持软删除拦截和只读保护.

    满足 ``BaseSyncBaseDAL[Session, DTOModelT, CUModelT, PrimaryKeyT]`` 协议.

    类型参数:
        DTOModelT: DTO 模型类型.
        CUModelT: CU 模型类型.
        PrimaryKeyT: 主键类型, 默认 ``int``.

    Args:
        table_ref: TableRef 表引用.
        dto_class: DTO 模型类.
        session: 可选, 构造注入的默认 session.
    """

    def __init__(
        self,
        table_ref: TableRef[PrimaryKeyT],
        dto_class: type[DTOModelT],
        session: Session | None = None,
    ) -> None:
        self._ref = table_ref
        self._DTO = dto_class
        self._session = session

    def _resolve_session(
        self,
        session: Session | NoSession,
    ) -> Session:
        """解析 session: 显式传入 > 构造注入."""
        if isinstance(session, NoSession):
            if self._session is None:
                raise RuntimeError("未提供 session: 请在构造时注入或调用时传入 session=<Session>")
            return self._session
        return session

    @classmethod
    def of(
        cls,
        table_ref: TableRef[PrimaryKeyT],
        dto_class: type[DTOModelT],
        *,
        session: Session | None = None,
    ) -> Self:
        """工厂方法 — 从 TableRef + DTO 创建.

        适用于不需要严格 CU 类型检查的场景.
        """
        return cls(table_ref, dto_class, session=session)

    # ── 读取 ───────────────────────────────────────────

    def get_by_id(
        self,
        entity_id: PrimaryKeyT,
        *,
        session: Session | NoSession = NO_SESSION,
    ) -> DTOModelT | None:
        """按主键获取实体 (自动过滤软删除).

        Args:
            entity_id: 主键值.
            session: SQLAlchemy Session, 默认使用构造注入值.

        Returns:
            DTO 实例, 未找到或已软删除时返回 ``None``.
        """
        s = self._resolve_session(session)
        stmt = self._ref.sa_table.select().where(self._ref.pk() == entity_id)
        stmt = self._ref.apply_select_filter(stmt)
        row = s.execute(stmt).mappings().first()
        if row is None:
            return None
        return self._DTO.model_validate(self._ref.map_from_row(dict(row)))

    def list_by(
        self,
        where: list[ColumnElement[bool]] | None = None,
        *,
        session: Session | NoSession = NO_SESSION,
        skip: int = 0,
        limit: int = 100,
        include_deleted: bool = False,
    ) -> list[DTOModelT]:
        """按条件查询列表 (自动过滤软删除).

        Args:
            where: 过滤条件列表, ``None`` 或空列表表示无额外条件.
            session: SQLAlchemy Session, 默认使用构造注入值.
            skip: 跳过条数.
            limit: 返回条数上限.
            include_deleted: 是否包含已软删除的记录.

        Returns:
            DTO 列表.
        """
        s = self._resolve_session(session)
        stmt = self._ref.sa_table.select()
        if where:
            for clause in where:
                stmt = stmt.where(clause)
        if not include_deleted:
            stmt = self._ref.apply_select_filter(stmt)
        stmt = stmt.offset(skip).limit(limit)
        rows = s.execute(stmt).mappings().all()
        return [self._DTO.model_validate(self._ref.map_from_row(dict(r))) for r in rows]

    def count_by(
        self,
        where: list[ColumnElement[bool]] | None = None,
        *,
        session: Session | NoSession = NO_SESSION,
        include_deleted: bool = False,
    ) -> int:
        """按条件计数 (自动过滤软删除).

        Args:
            where: 过滤条件列表.
            session: SQLAlchemy Session, 默认使用构造注入值.
            include_deleted: 是否包含已软删除的记录.

        Returns:
            满足条件的记录数.
        """
        s = self._resolve_session(session)
        stmt = sa.select(sa.func.count()).select_from(self._ref.sa_table)
        if where:
            for clause in where:
                stmt = stmt.where(clause)
        if not include_deleted:
            stmt = self._ref.apply_select_filter(stmt)
        return s.execute(stmt).scalar() or 0

    # ── 写入 ───────────────────────────────────────────

    def create(
        self,
        cu: CUModelT,
        *,
        session: Session | NoSession = NO_SESSION,
    ) -> DTOModelT:
        """创建记录.

        Args:
            cu: CU 模型实例.
            session: SQLAlchemy Session, 默认使用构造注入值.

        Returns:
            创建后的 DTO 实例.

        Raises:
            TypeError: 表被标记为只读时.
        """
        s = self._resolve_session(session)
        self._ref.guard_readonly("创建")
        row_data = self._ref.cu_row_data(cu)
        result: Result[Any] = s.execute(self._ref.sa_table.insert().values(**row_data))
        pk_value = self._ref.resolve_pk(result)
        if pk_value is None:
            raise RuntimeError(f"创建后无法获取主键: table={self._ref.table_name}")
        created = self.get_by_id(pk_value, session=s)
        if created is None:
            raise RuntimeError(f"创建后读取失败: table={self._ref.table_name}, pk={pk_value}")
        return created

    def update_by_id(
        self,
        entity_id: PrimaryKeyT,
        cu: CUModelT,
        *,
        session: Session | NoSession = NO_SESSION,
    ) -> int:
        """按主键更新记录 (仅更新 CU 中已设置的字段).

        Args:
            entity_id: 主键值.
            cu: CU 模型实例.
            session: SQLAlchemy Session, 默认使用构造注入值.

        Returns:
            受影响的行数.

        Raises:
            TypeError: 表被标记为只读时.
        """
        s = self._resolve_session(session)
        self._ref.guard_readonly("更新")
        row_data = self._ref.cu_row_data(cu)
        if not row_data:
            return 0
        stmt = self._ref.sa_table.update().where(self._ref.pk() == entity_id).values(**row_data)
        result: Result[Any] = s.execute(stmt)
        return getattr(result, "rowcount", 0)

    def delete_by_id(
        self,
        entity_id: PrimaryKeyT,
        *,
        session: Session | NoSession = NO_SESSION,
    ) -> bool:
        """按主键删除记录.

        配置了软删除列时执行 ``UPDATE SET sd_col=sd_value``, 否则执行 ``DELETE``.

        Args:
            entity_id: 主键值.
            session: SQLAlchemy Session, 默认使用构造注入值.

        Returns:
            是否成功删除 (或软删除).

        Raises:
            TypeError: 表被标记为只读时.
        """
        s = self._resolve_session(session)
        cfg = self._ref.config
        self._ref.guard_readonly("删除")
        if cfg.soft_delete_column is not None:
            stmt = self._ref.sa_table.update().where(self._ref.pk() == entity_id).values(**{cfg.soft_delete_column: cfg.soft_delete_value})
        else:
            stmt = self._ref.sa_table.delete().where(self._ref.pk() == entity_id)
        result: Result[Any] = s.execute(stmt)
        return getattr(result, "rowcount", 0) > 0

    def restore_by_id(
        self,
        entity_id: PrimaryKeyT,
        *,
        session: Session | NoSession = NO_SESSION,
    ) -> bool:
        """恢复软删除的记录.

        Args:
            entity_id: 主键值.
            session: SQLAlchemy Session, 默认使用构造注入值.

        Returns:
            是否成功恢复.

        Raises:
            TypeError: 表未配置软删除时, 或表被标记为只读时.
        """
        s = self._resolve_session(session)
        cfg = self._ref.config
        if cfg.soft_delete_column is None:
            raise TypeError(f"表 '{self._ref.table_name}' 未配置软删除, 无法恢复")
        self._ref.guard_readonly("恢复")
        stmt = self._ref.sa_table.update().where(self._ref.pk() == entity_id).values(**{cfg.soft_delete_column: cfg.soft_undelete_value})
        result: Result[Any] = s.execute(stmt)
        return getattr(result, "rowcount", 0) > 0

    def bulk_create(
        self,
        cus: Iterable[CUModelT],
        *,
        session: Session | NoSession = NO_SESSION,
    ) -> int:
        """批量创建记录.

        Args:
            cus: CU 模型实例列表.
            session: SQLAlchemy Session, 默认使用构造注入值.

        Returns:
            创建的记录数.

        Raises:
            TypeError: 表被标记为只读时.
        """
        s = self._resolve_session(session)
        self._ref.guard_readonly("批量创建")
        rows = [self._ref.cu_row_data(cu) for cu in cus]
        if not rows:
            return 0
        _ = s.execute(self._ref.sa_table.insert(), rows)
        return len(rows)


# ---------------------------------------------------------------------------
# DynamicAsyncDAL
# ---------------------------------------------------------------------------


class DynamicAsyncDAL(
    BaseAsyncBaseDAL[AsyncSession, DTOModelT, CUModelT, PrimaryKeyT],
    Generic[DTOModelT, CUModelT, PrimaryKeyT],
):
    """无需 Table class 的异步动态 DAL — ``DynamicSyncDAL`` 的异步镜像.

    满足 ``BaseAsyncBaseDAL[AsyncSession, DTOModelT, CUModelT, PrimaryKeyT]`` 协议.

    类型参数:
        DTOModelT: DTO 模型类型.
        CUModelT: CU 模型类型.
        PrimaryKeyT: 主键类型, 默认 ``int``.

    Args:
        table_ref: TableRef 表引用.
        dto_class: DTO 模型类.
        session: 可选, 构造注入的默认 session.
    """

    def __init__(
        self,
        table_ref: TableRef[PrimaryKeyT],
        dto_class: type[DTOModelT],
        session: AsyncSession | None = None,
    ) -> None:
        self._ref = table_ref
        self._DTO = dto_class
        self._session = session

    def _resolve_session(
        self,
        session: AsyncSession | NoSession,
    ) -> AsyncSession:
        """解析 session: 显式传入 > 构造注入."""
        if isinstance(session, NoSession):
            if self._session is None:
                raise RuntimeError("未提供 session: 请在构造时注入或调用时传入 session=<AsyncSession>")
            return self._session
        return session

    @classmethod
    def of(
        cls,
        table_ref: TableRef[PrimaryKeyT],
        dto_class: type[DTOModelT],
        *,
        session: AsyncSession | None = None,
    ) -> Self:
        """工厂方法 — 从 TableRef + DTO 创建.

        适用于不需要严格 CU 类型检查的场景.
        """
        return cls(table_ref, dto_class, session=session)

    # ── 读取 ───────────────────────────────────────────

    async def get_by_id(
        self,
        entity_id: PrimaryKeyT,
        *,
        session: AsyncSession | NoSession = NO_SESSION,
    ) -> DTOModelT | None:
        """按主键获取实体 (自动过滤软删除)."""
        s = self._resolve_session(session)
        stmt = self._ref.sa_table.select().where(self._ref.pk() == entity_id)
        stmt = self._ref.apply_select_filter(stmt)
        result = await s.execute(stmt)
        row = result.mappings().first()
        if row is None:
            return None
        return self._DTO.model_validate(self._ref.map_from_row(dict(row)))

    async def list_by(
        self,
        where: list[ColumnElement[bool]] | None = None,
        *,
        session: AsyncSession | NoSession = NO_SESSION,
        skip: int = 0,
        limit: int = 100,
        include_deleted: bool = False,
    ) -> list[DTOModelT]:
        """按条件查询列表 (自动过滤软删除)."""
        s = self._resolve_session(session)
        stmt = self._ref.sa_table.select()
        if where:
            for clause in where:
                stmt = stmt.where(clause)
        if not include_deleted:
            stmt = self._ref.apply_select_filter(stmt)
        stmt = stmt.offset(skip).limit(limit)
        result = await s.execute(stmt)
        rows = result.mappings().all()
        return [self._DTO.model_validate(self._ref.map_from_row(dict(r))) for r in rows]

    async def count_by(
        self,
        where: list[ColumnElement[bool]] | None = None,
        *,
        session: AsyncSession | NoSession = NO_SESSION,
        include_deleted: bool = False,
    ) -> int:
        """按条件计数 (自动过滤软删除)."""
        s = self._resolve_session(session)
        stmt = sa.select(sa.func.count()).select_from(self._ref.sa_table)
        if where:
            for clause in where:
                stmt = stmt.where(clause)
        if not include_deleted:
            stmt = self._ref.apply_select_filter(stmt)
        result = await s.execute(stmt)
        return result.scalar() or 0

    # ── 写入 ───────────────────────────────────────────

    async def create(
        self,
        cu: CUModelT,
        *,
        session: AsyncSession | NoSession = NO_SESSION,
    ) -> DTOModelT:
        """创建记录."""
        s = self._resolve_session(session)
        self._ref.guard_readonly("创建")
        row_data = self._ref.cu_row_data(cu)
        result: Result[Any] = await s.execute(self._ref.sa_table.insert().values(**row_data))
        pk_value = self._ref.resolve_pk(result)
        if pk_value is None:
            raise RuntimeError(f"创建后无法获取主键: table={self._ref.table_name}")
        created = await self.get_by_id(pk_value, session=s)
        if created is None:
            raise RuntimeError(f"创建后读取失败: table={self._ref.table_name}, pk={pk_value}")
        return created

    async def update_by_id(
        self,
        entity_id: PrimaryKeyT,
        cu: CUModelT,
        *,
        session: AsyncSession | NoSession = NO_SESSION,
    ) -> int:
        """按主键更新记录."""
        s = self._resolve_session(session)
        self._ref.guard_readonly("更新")
        row_data = self._ref.cu_row_data(cu)
        if not row_data:
            return 0
        stmt = self._ref.sa_table.update().where(self._ref.pk() == entity_id).values(**row_data)
        result: Result[Any] = await s.execute(stmt)
        return getattr(result, "rowcount", 0)

    async def delete_by_id(
        self,
        entity_id: PrimaryKeyT,
        *,
        session: AsyncSession | NoSession = NO_SESSION,
    ) -> bool:
        """按主键删除记录 (软删除 or 硬删除)."""
        s = self._resolve_session(session)
        cfg = self._ref.config
        self._ref.guard_readonly("删除")
        if cfg.soft_delete_column is not None:
            stmt = self._ref.sa_table.update().where(self._ref.pk() == entity_id).values(**{cfg.soft_delete_column: cfg.soft_delete_value})
        else:
            stmt = self._ref.sa_table.delete().where(self._ref.pk() == entity_id)
        result: Result[Any] = await s.execute(stmt)
        return getattr(result, "rowcount", 0) > 0

    async def restore_by_id(
        self,
        entity_id: PrimaryKeyT,
        *,
        session: AsyncSession | NoSession = NO_SESSION,
    ) -> bool:
        """恢复软删除的记录."""
        s = self._resolve_session(session)
        cfg = self._ref.config
        if cfg.soft_delete_column is None:
            raise TypeError(f"表 '{self._ref.table_name}' 未配置软删除, 无法恢复")
        self._ref.guard_readonly("恢复")
        stmt = self._ref.sa_table.update().where(self._ref.pk() == entity_id).values(**{cfg.soft_delete_column: cfg.soft_undelete_value})
        result: Result[Any] = await s.execute(stmt)
        return getattr(result, "rowcount", 0) > 0

    async def bulk_create(
        self,
        cus: Iterable[CUModelT],
        *,
        session: AsyncSession | NoSession = NO_SESSION,
    ) -> int:
        """批量创建记录."""
        s = self._resolve_session(session)
        self._ref.guard_readonly("批量创建")
        rows = [self._ref.cu_row_data(cu) for cu in cus]
        if not rows:
            return 0
        _ = await s.execute(self._ref.sa_table.insert(), rows)
        return len(rows)


__all__ = (
    "DynamicAsyncDAL",
    "DynamicSyncDAL",
    "DynamicTableConfig",
    "PrimaryKeyT",
    "TableRef",
    "derive_columns_from_dto",
    "derive_pk_from_dto",
)
