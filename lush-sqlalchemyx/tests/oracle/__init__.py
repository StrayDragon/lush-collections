"""软删除可见性 oracle — 纯 SQLAlchemy Core, 不依赖 DAL hooks / mixin."""

from .soft_delete import (
    SoftDeleteStyle,
    oracle_count_visible_rows,
    oracle_is_soft_deleted_row,
    oracle_select_raw_by_id,
    oracle_select_visible_by_id,
)

__all__ = (
    "SoftDeleteStyle",
    "oracle_count_visible_rows",
    "oracle_is_soft_deleted_row",
    "oracle_select_raw_by_id",
    "oracle_select_visible_by_id",
)
