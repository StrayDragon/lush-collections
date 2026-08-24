"""``BaseCU.cu_config`` MRO 浅合并的属性测试 (docs/design/11 §4).

不变量:
- ``resolve_cu_config()`` 结果恒含两个键 (to_orm_exclude / update_exclude)
- 未设键回落 BaseCU 默认 ({"id"})
- 子类已设键覆盖上游, 未设键继承上游 (浅合并)
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lush_dal_protocol.dto import BaseCU

pytestmark = pytest.mark.property

_PK_NAMES = st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]{0,23}", fullmatch=True)


def _make_cu_class(name: str, /, *, base: type, cu_config: dict | None = None) -> type:
    namespace: dict[str, object] = {"_Table": object, "__module__": __name__}
    if cu_config is not None:
        namespace["cu_config"] = cu_config
    return type(name, (base,), namespace)


@given(_PK_NAMES)
def test_property__resolved_config_always_two_keys(pk_field: str) -> None:
    """未显式声明 cu_config 的子类也必然拿到完整双键默认配置."""
    cls = _make_cu_class("SoloCU", base=BaseCU)
    resolved = cls.resolve_cu_config()  # type: ignore[attr-defined]
    assert set(resolved.keys()) == {"to_orm_exclude", "update_exclude"}
    assert resolved["to_orm_exclude"] == frozenset({"id"})
    assert resolved["update_exclude"] == frozenset({"id"})


@given(_PK_NAMES, _PK_NAMES)
def test_property__mro_shallow_merge_child_wins(pk_parent: str, pk_child: str) -> None:
    """子类仅设 update_exclude 时: to_orm 继承父类, update 覆盖为子类值."""
    parent = _make_cu_class("ParentCU", base=BaseCU, cu_config={"to_orm_exclude": frozenset({pk_parent})})
    child = _make_cu_class("ChildCU", base=parent, cu_config={"update_exclude": frozenset({pk_child})})
    resolved = child.resolve_cu_config()
    assert resolved["to_orm_exclude"] == frozenset({pk_parent})
    assert resolved["update_exclude"] == frozenset({pk_child})
    # 父类自身未设的键回落默认
    parent_resolved = parent.resolve_cu_config()
    assert parent_resolved["update_exclude"] == frozenset({"id"})


@given(_PK_NAMES)
def test_property__grandchild_inherits_without_redeclare(pk_field: str) -> None:
    """隔代继承: 孙类不重声明时沿用父类合并结果 (缓存不被中间层破坏)."""
    parent = _make_cu_class("ParentCU", base=BaseCU, cu_config={"to_orm_exclude": frozenset({pk_field})})
    mid = _make_cu_class("MidCU", base=parent)
    grandchild = _make_cu_class("GrandChildCU", base=mid)
    assert grandchild.resolve_cu_config()["to_orm_exclude"] == frozenset({pk_field})
