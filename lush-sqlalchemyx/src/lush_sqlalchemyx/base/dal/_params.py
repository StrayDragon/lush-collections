"""SQLAlchemy 特定的操作扩展参数.

继承 lush-dal-protocol 的 ``Extra`` 基类, 添加 SQLAlchemy 特有选项.
所有 V2 DAL 方法的 ``extra`` 参数均使用此类型.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from lush_dal_protocol.params import Extra


@dataclass(frozen=True)
class SQLAExtra(Extra):
    """SQLAlchemy 操作扩展参数.

    字段按操作类别分组, 各方法按需读取相关字段::

        extra = SQLAExtra(lock_timeout=5, need_refresh=True)
        DAL.get_by_id_for_update(session, entity_id, extra)
    """

    lock_timeout: int | None = None
    need_refresh: bool = False
    version_field: str = "version"
    strict_missing: bool = True
    none_policy: Literal["ignore", "allow", "forbid"] = "ignore"
    strict: bool = False
    fields: Any = None
    none_policy_overrides: dict[Any, Literal["ignore", "allow", "forbid"]] | None = None
