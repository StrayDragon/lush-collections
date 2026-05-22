"""更新操作参数对象."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class UpdateOptions:
    """全量更新选项."""

    need_refresh: bool = False
    strict_missing: bool = True


@dataclass(frozen=True)
class PartialUpdateOptions:
    """部分更新选项."""

    need_refresh: bool = False
    none_policy: Literal["ignore", "allow", "forbid"] = "ignore"
    strict: bool = False
