"""主键属性与审计列去魔法 — Core oracle (不依赖 DAL).

期望语义:
- Core UPDATE 仅 SET 显式传入的列; 不得隐式带 ``update_datetime`` / ``update_operator_id``
- 按 ``pk_attr`` (默认 ``id``) 定位行; 自定义主键列名亦可
"""

from __future__ import annotations

import re
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session


def _table(table_cls: type[Any]) -> sa.Table:
    return sa.inspect(table_cls).local_table


def oracle_compiled_sql(stmt: Any) -> str:
    """将 SQLAlchemy 语句编译为可读 SQL 字符串."""
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def oracle_update_set_clause(stmt: Any) -> str:
    """返回 UPDATE 语句 SET 段 (WHERE 之前), 小写."""
    sql = oracle_compiled_sql(stmt).lower()
    if " where " in sql:
        return sql.split(" where ", 1)[0]
    return sql


def oracle_update_sets_column(stmt: Any, column_name: str) -> bool:
    """判断 UPDATE 的 SET 段是否对指定列赋值 (避免表名误匹配)."""
    set_clause = oracle_update_set_clause(stmt)
    return oracle_raw_sql_sets_column(set_clause, column_name)


def oracle_raw_sql_sets_column(sql: str, column_name: str) -> bool:
    """对原始 / 编译 SQL 字符串判断 SET 是否给某列赋值."""
    lower = sql.lower()
    set_clause = lower.split(" where ", 1)[0] if " where " in lower else lower
    return re.search(rf"(?:^update\s+\S+\s+set\s+|^set\s+|,\s*){re.escape(column_name.lower())}\s*=", set_clause) is not None


def oracle_update_by_pk(
    session: Session,
    table_cls: type[Any],
    pk_value: Any,
    *,
    values: dict[str, Any],
    pk_attr: str = "id",
) -> int:
    """Core UPDATE: WHERE pk=:pk, SET 仅 ``values`` 中的列."""
    table = _table(table_cls)
    pk_col = table.c[pk_attr]
    result = session.execute(sa.update(table).where(pk_col == pk_value).values(**values))
    session.flush()
    return int(getattr(result, "rowcount", 0) or 0)


def oracle_select_by_pk(
    session: Session,
    table_cls: type[Any],
    pk_value: Any,
    *,
    pk_attr: str = "id",
) -> dict[str, Any] | None:
    """Core SELECT 按主键取物理行."""
    table = _table(table_cls)
    pk_col = table.c[pk_attr]
    row = session.execute(sa.select(table).where(pk_col == pk_value)).mappings().one_or_none()
    return dict(row) if row is not None else None


def oracle_insert_row(
    session: Session,
    table_cls: type[Any],
    *,
    values: dict[str, Any],
) -> Any:
    """Core INSERT 一行, 返回主键 (单列 PK)."""
    table = _table(table_cls)
    result = session.execute(sa.insert(table).values(**values))
    session.flush()
    pk = result.inserted_primary_key
    assert pk is not None and pk[0] is not None
    return pk[0]
