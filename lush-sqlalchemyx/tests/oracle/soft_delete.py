"""软删除可见性 oracle — 纯 SQLAlchemy Core, 不依赖 DAL hooks / mixin.

期望语义:
- 标准 ``is_delete`` 列: ``WHERE is_delete = 0`` 为可见
- 自定义 ``deleted_at`` 列: ``WHERE deleted_at IS NULL`` 为可见
"""

from __future__ import annotations

from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session

SoftDeleteStyle = Literal["is_delete", "deleted_at"]


def _table(table_cls: type[Any]) -> sa.Table:
    return sa.inspect(table_cls).local_table


def _visible_predicate(table: sa.Table, style: SoftDeleteStyle) -> Any:
    if style == "is_delete":
        return table.c.is_delete == 0
    if style == "deleted_at":
        return table.c.deleted_at.is_(None)
    raise ValueError(f"unsupported soft-delete style: {style!r}")


def oracle_select_visible_by_id(
    session: Session,
    table_cls: type[Any],
    entity_id: int,
    *,
    style: SoftDeleteStyle = "is_delete",
) -> dict[str, Any] | None:
    """Core SELECT 按主键取可见行; 返回 row mapping 或 None."""
    table = _table(table_cls)
    stmt = sa.select(table).where(table.c.id == entity_id, _visible_predicate(table, style))
    row = session.execute(stmt).mappings().one_or_none()
    return dict(row) if row is not None else None


def oracle_select_raw_by_id(
    session: Session,
    table_cls: type[Any],
    entity_id: int,
) -> dict[str, Any] | None:
    """Core SELECT 按主键取物理行 (含已软删除), 不施加可见性过滤."""
    table = _table(table_cls)
    stmt = sa.select(table).where(table.c.id == entity_id)
    row = session.execute(stmt).mappings().one_or_none()
    return dict(row) if row is not None else None


def oracle_count_visible_rows(
    session: Session,
    table_cls: type[Any],
    *,
    style: SoftDeleteStyle = "is_delete",
) -> int:
    """Core COUNT 可见行."""
    table = _table(table_cls)
    stmt = sa.select(sa.func.count()).select_from(table).where(_visible_predicate(table, style))
    return session.execute(stmt).scalar_one()


def oracle_is_soft_deleted_row(row: dict[str, Any], *, style: SoftDeleteStyle) -> bool:
    """根据物理行判断是否已软删除 (纯字段语义, 不走 mixin)."""
    if style == "is_delete":
        return int(row.get("is_delete", 0)) != 0
    if style == "deleted_at":
        return row.get("deleted_at") is not None
    raise ValueError(f"unsupported soft-delete style: {style!r}")
