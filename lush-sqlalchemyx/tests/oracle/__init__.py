"""oracle 辅助: 软删除可见性 / 1:1 扩展表共享主键 — 纯 SQLAlchemy Core."""

from .extend_table import (
    async_oracle_count_rows,
    async_oracle_insert_extend_row,
    async_oracle_insert_main_row,
    async_oracle_select_raw_sql,
    async_oracle_select_row_by_id,
    async_oracle_update_extend_row,
    oracle_count_rows,
    oracle_insert_extend_row,
    oracle_insert_main_row,
    oracle_select_row_by_id,
    oracle_update_extend_row,
)
from .soft_delete import (
    SoftDeleteStyle,
    oracle_count_visible_rows,
    oracle_is_soft_deleted_row,
    oracle_select_raw_by_id,
    oracle_select_visible_by_id,
)

__all__ = (
    "SoftDeleteStyle",
    "async_oracle_count_rows",
    "async_oracle_insert_extend_row",
    "async_oracle_insert_main_row",
    "async_oracle_select_raw_sql",
    "async_oracle_select_row_by_id",
    "async_oracle_update_extend_row",
    "oracle_count_rows",
    "oracle_count_visible_rows",
    "oracle_insert_extend_row",
    "oracle_insert_main_row",
    "oracle_is_soft_deleted_row",
    "oracle_select_raw_by_id",
    "oracle_select_row_by_id",
    "oracle_select_visible_by_id",
    "oracle_update_extend_row",
)
