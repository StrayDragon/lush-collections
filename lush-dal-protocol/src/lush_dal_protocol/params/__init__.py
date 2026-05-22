"""ORM 无关的操作参数对象.

下游适配包可通过继承 ``Extra`` 扩展, 添加 ORM 特有选项.
"""

from .extra import Extra, ExtraT

__all__ = [
    "Extra",
    "ExtraT",
]
