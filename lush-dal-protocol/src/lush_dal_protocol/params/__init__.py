"""ORM 无关的操作参数对象.

下游适配包可通过继承扩展, 添加 ORM 特有选项.
"""

from .lock import LockOptions, OptimisticLockOptions
from .update import PartialUpdateOptions, UpdateOptions

__all__ = [
    "LockOptions",
    "OptimisticLockOptions",
    "PartialUpdateOptions",
    "UpdateOptions",
]
