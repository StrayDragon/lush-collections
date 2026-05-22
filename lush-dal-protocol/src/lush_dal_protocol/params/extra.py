"""统一操作扩展参数基类."""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import TypeVar


@dataclass(frozen=True)
class Extra:
    """操作扩展参数基类.

    所有 ABC 方法的 ``extra`` 参数均使用此类型或其子类.
    下游 ORM 适配包可继承并添加 ORM/业务特有字段::

        @dataclass(frozen=True)
        class SQLAExtra(Extra):
            lock_timeout: int | None = None
            with_for_update: bool = False
    """


ExtraT = TypeVar("ExtraT", bound=Extra, default=Extra)
