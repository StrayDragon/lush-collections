"""1:1 扩展表 (共享主键) oracle — 纯 SQLAlchemy Core, 不依赖 DAL / cu_config.

期望语义:
- 主表 INSERT 自增 PK
- 扩展表 INSERT 显式写入与主表相同的 id (非自增)
- 扩展表 UPDATE 按主键定位, SET 不含 id (即使业务层误传了另一 id)

提供 sync ``Session`` 与 async ``AsyncSession`` 两套 API.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session


def _table(table_cls: type[Any]) -> sa.Table:
    return sa.inspect(table_cls).local_table


def oracle_insert_main_row(session: Session, table_cls: type[Any], *, stage: str) -> int:
    """Core INSERT 主表一行, 返回自增 id."""
    table = _table(table_cls)
    result = session.execute(sa.insert(table).values(stage=stage))
    session.flush()
    pk = result.inserted_primary_key
    assert pk is not None and pk[0] is not None
    return int(pk[0])


def oracle_insert_extend_row(
    session: Session,
    table_cls: type[Any],
    *,
    entity_id: int,
    report_name: str,
) -> None:
    """Core INSERT 扩展表一行, 显式写入共享主键."""
    table = _table(table_cls)
    session.execute(sa.insert(table).values(id=entity_id, report_name=report_name))
    session.flush()


def oracle_update_extend_row(
    session: Session,
    table_cls: type[Any],
    entity_id: int,
    *,
    report_name: str,
) -> int:
    """Core UPDATE 扩展表: WHERE id=:entity_id, SET 仅业务列 (不含 id)."""
    table = _table(table_cls)
    result = session.execute(sa.update(table).where(table.c.id == entity_id).values(report_name=report_name))
    session.flush()
    return int(getattr(result, "rowcount", 0) or 0)


def oracle_select_row_by_id(
    session: Session,
    table_cls: type[Any],
    entity_id: int,
) -> dict[str, Any] | None:
    """Core SELECT 按主键取物理行."""
    table = _table(table_cls)
    row = session.execute(sa.select(table).where(table.c.id == entity_id)).mappings().one_or_none()
    return dict(row) if row is not None else None


def oracle_count_rows(session: Session, table_cls: type[Any]) -> int:
    """Core COUNT 全表行数."""
    table = _table(table_cls)
    return int(session.execute(sa.select(sa.func.count()).select_from(table)).scalar_one())


async def async_oracle_insert_main_row(session: AsyncSession, table_cls: type[Any], *, stage: str) -> int:
    """异步 Core INSERT 主表一行, 返回自增 id."""
    table = _table(table_cls)
    result = await session.execute(sa.insert(table).values(stage=stage))
    await session.flush()
    pk = result.inserted_primary_key
    assert pk is not None and pk[0] is not None
    return int(pk[0])


async def async_oracle_insert_extend_row(
    session: AsyncSession,
    table_cls: type[Any],
    *,
    entity_id: int,
    report_name: str,
) -> None:
    """异步 Core INSERT 扩展表一行, 显式写入共享主键."""
    table = _table(table_cls)
    await session.execute(sa.insert(table).values(id=entity_id, report_name=report_name))
    await session.flush()


async def async_oracle_update_extend_row(
    session: AsyncSession,
    table_cls: type[Any],
    entity_id: int,
    *,
    report_name: str,
) -> int:
    """异步 Core UPDATE 扩展表: WHERE id=:entity_id, SET 仅业务列 (不含 id)."""
    table = _table(table_cls)
    result = await session.execute(sa.update(table).where(table.c.id == entity_id).values(report_name=report_name))
    await session.flush()
    return int(getattr(result, "rowcount", 0) or 0)


async def async_oracle_select_row_by_id(
    session: AsyncSession,
    table_cls: type[Any],
    entity_id: int,
) -> dict[str, Any] | None:
    """异步 Core SELECT 按主键取物理行."""
    table = _table(table_cls)
    row = (await session.execute(sa.select(table).where(table.c.id == entity_id))).mappings().one_or_none()
    return dict(row) if row is not None else None


async def async_oracle_count_rows(session: AsyncSession, table_cls: type[Any]) -> int:
    """异步 Core COUNT 全表行数."""
    table = _table(table_cls)
    return int((await session.execute(sa.select(sa.func.count()).select_from(table))).scalar_one())


async def async_oracle_select_raw_sql(
    session: AsyncSession,
    sql: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """异步执行裸 SQL SELECT 单行 (Dynamic 表无 ORM class 时用)."""
    row = (await session.execute(sa.text(sql), params or {})).mappings().one_or_none()
    return dict(row) if row is not None else None
