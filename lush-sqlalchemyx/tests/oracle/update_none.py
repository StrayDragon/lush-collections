"""UPDATE 写入 None / dirty 属性 oracle — 纯 SQLAlchemy ORM, 不依赖 DAL.

期望语义:
- ``setattr(entity, key, None)`` 与 ``entity.key = None`` 走同一 ``InstrumentedAttribute.__set__``
- 二者都会把属性标 dirty, flush 时发出 ``SET col = NULL``
- 不会因赋值语法不同而跳过列或改写为 server ON UPDATE
"""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

AssignStyle = Literal["setattr", "dot"]
"""赋值风格: ``setattr`` 与 descriptor ``__set__`` (点号赋值等价路径)."""


def oracle_assign_attr(entity: Any, key: str, value: Any, *, style: AssignStyle) -> None:
    """按指定风格给已映射实体赋值 (与 DAL 的 setattr 路径对拍).

    ``dot`` 不能写字面量 ``entity.xxx`` (属性名动态), 且不可用 ``object.__setattr__``
    (会绕过 ORM descriptor); 正确做法是调用 ``InstrumentedAttribute.__set__``.
    """
    if style == "setattr":
        setattr(entity, key, value)
        return
    getattr(type(entity), key).__set__(entity, value)


def oracle_attr_is_dirty(entity: Any, key: str) -> bool:
    """检查属性是否被 ORM 标为 dirty (``history.added`` / ``deleted`` 任一非空)."""
    hist = sa_inspect(entity).attrs[key].history
    return bool(hist.added) or bool(hist.deleted)


def oracle_flush_assign_none(session: Session, entity: Any, key: str, *, style: AssignStyle) -> None:
    """对已持久化实体赋 ``None`` 并 flush (断言赋值后属性已 dirty)."""
    oracle_assign_attr(entity, key, None, style=style)
    assert oracle_attr_is_dirty(entity, key)
    session.flush()
