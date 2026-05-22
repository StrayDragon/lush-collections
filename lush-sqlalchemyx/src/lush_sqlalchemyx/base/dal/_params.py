"""SQLAlchemy 特定的操作参数对象.

继承 lush-dal-protocol 的通用参数对象, 添加 SQLAlchemy 特有选项.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from lush_dal_protocol.params import (
    LockOptions,
    OptimisticLockOptions,
    PartialUpdateOptions,
    UpdateOptions,
)


@dataclass(frozen=True)
class SQLALockOptions(LockOptions):
    """SQLAlchemy 悲观锁选项."""


@dataclass(frozen=True)
class SQLAOptimisticLockOptions(OptimisticLockOptions):
    """SQLAlchemy 乐观锁选项."""


@dataclass(frozen=True)
class SQLAUpdateOptions(UpdateOptions):
    """SQLAlchemy 全量更新选项."""


@dataclass(frozen=True)
class SQLAPartialUpdateOptions(PartialUpdateOptions):
    """SQLAlchemy 部分更新选项.

    扩展了 ORM 特有的 fields / none_policy_overrides.
    """

    fields: Any = None
    none_policy_overrides: dict[Any, Literal["ignore", "allow", "forbid"]] | None = None
