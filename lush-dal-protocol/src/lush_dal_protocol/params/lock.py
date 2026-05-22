"""锁操作参数对象."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LockOptions:
    """悲观锁操作选项.

    下游可继承扩展 ORM 特有字段 (如 nowait / skip_locked 等).
    """

    timeout: int | None = None


@dataclass(frozen=True)
class OptimisticLockOptions:
    """乐观锁操作选项."""

    version_field: str = "version"
    need_refresh: bool = False
