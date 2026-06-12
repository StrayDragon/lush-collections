"""BDD 步骤定义 — MetaInfoEnum 继承与扩展.

架构
~~~~

- 所有枚举类均为进程内定义, 无外部依赖
- Given: 通过 fixture registry 注入具体枚举类
- Then: 直接验证枚举成员的属性和行为

步骤覆盖三大场景:
1. 基本继承 — 直接继承 MetaInfoIntEnum / MetaInfoStrEnum
2. 扩展 XMetaInfo — 子类化 XMetaInfo + override x_meta 返回类型
3. 中间基类 — 定义一次覆盖, 所有子类复用
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, then

from lush_stdx.enumx import MetaInfoIntEnum, MetaInfoStrEnum, XMetaInfo


def _try_int(s: str) -> int | str:
    """尝试将字符串转为 int, 失败则返回原值."""
    try:
        return int(s)
    except ValueError:
        return s


# ════════════════════════════════════════════════════════════════
# 枚举注册表 — Gherkin 中的名字映射到预定义类
# ════════════════════════════════════════════════════════════════


# -- 基本 IntEnum --
class _BasicInt(MetaInfoIntEnum):
    PENDING = 1, XMetaInfo("等待中")
    DONE = 2, XMetaInfo("已完成")


class _Priority(MetaInfoIntEnum):
    LOW = 0, XMetaInfo("低优先级")
    HIGH = 1, XMetaInfo("高优先级")


# -- 基本 StrEnum --
class _BasicStr(MetaInfoStrEnum):
    VANILLA = "vanilla", XMetaInfo("香草味")
    CHOCOLATE = "chocolate", XMetaInfo("巧克力味")


# -- 扩展 XMetaInfo (IntEnum) -- 使用 _x_meta 声明触发 __init_subclass__ 自动生成窄化 property --
@dataclasses.dataclass(frozen=True, slots=True)
class _ColorMeta(XMetaInfo):
    color: str = ""
    order: int = 0


class _ExtendedInt(MetaInfoIntEnum):
    _x_meta: _ColorMeta  # pyright: ignore[reportIncompatibleVariableOverride]

    RED = 1, _ColorMeta("红色", color="#ff0000", order=1)
    GREEN = 2, _ColorMeta("绿色", color="#00ff00", order=2)


# -- 扩展 XMetaInfo (StrEnum) --
@dataclasses.dataclass(frozen=True, slots=True)
class _IconMeta(XMetaInfo):
    icon: str = ""


class _ExtendedStr(MetaInfoStrEnum):
    _x_meta: _IconMeta  # pyright: ignore[reportIncompatibleVariableOverride]

    SUCCESS = "success", _IconMeta("成功", icon="✅")
    WARNING = "warning", _IconMeta("警告", icon="⚠️")


# -- 中间基类 — 使用 _x_meta 声明, __init_subclass__ 自动生成窄化 property --
@dataclasses.dataclass(frozen=True, slots=True)
class _BizMeta(XMetaInfo):
    badge: str = ""
    css_class: str = ""


class _AppIntEnum(MetaInfoIntEnum):
    _x_meta: _BizMeta  # pyright: ignore[reportIncompatibleVariableOverride]

    # 自动获得 .x_meta -> _BizMeta, 无需手动 @property


class _OrderStatus(_AppIntEnum):
    PENDING = 1, _BizMeta("待支付", badge="⏳", css_class="label-warning")
    SHIPPED = 2, _BizMeta("已发货", badge="📦", css_class="label-info")


class _PaymentMethod(_AppIntEnum):
    WECHAT = 1, _BizMeta("微信支付", badge="💚", css_class="label-green")
    ALIPAY = 2, _BizMeta("支付宝", badge="💙", css_class="label-blue")


_ENUM_REGISTRY: dict[str, type] = {
    "basic_int": _BasicInt,
    "basic_str": _BasicStr,
    "priority": _Priority,
    "extended_int": _ExtendedInt,
    "extended_str": _ExtendedStr,
    "order_status": _OrderStatus,
    "payment_method": _PaymentMethod,
}


# ════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════


@pytest.fixture
def bdd_context() -> dict[str, Any]:
    return {}


# ════════════════════════════════════════════════════════════════
# Given 步骤
# ════════════════════════════════════════════════════════════════


@given("枚举测试 fixture 已就绪")
def given_fixture_ready() -> None:
    pass


@given(parsers.parse('存在 MetaInfoIntEnum 子类 "{registry_name}"'))
@given(parsers.parse('存在 MetaInfoStrEnum 子类 "{registry_name}"'))
@given(parsers.parse('存在带扩展 meta 的 IntEnum 子类 "{registry_name}"'))
@given(parsers.parse('存在带扩展 meta 的 StrEnum 子类 "{registry_name}"'))
@given(parsers.parse('存在通过中间基类定义的 IntEnum 子类 "{registry_name}"'))
def given_enum_in_context(bdd_context: dict[str, Any], registry_name: str) -> None:
    bdd_context["current_enum_name"] = registry_name


# ════════════════════════════════════════════════════════════════
# When 步骤
# ════════════════════════════════════════════════════════════════

# 基本继承场景不涉及 When (直接 Then 断言)

# ════════════════════════════════════════════════════════════════
# Then 步骤 — 所有断言
# ════════════════════════════════════════════════════════════════


def _resolve_enum(ctx: dict[str, Any], enum_name: str = "") -> type:
    name = enum_name or ctx["current_enum_name"]
    if name not in _ENUM_REGISTRY:
        raise ValueError(f"未知枚举: {name!r}, 可用: {list(_ENUM_REGISTRY)}")
    return _ENUM_REGISTRY[name]


def _member(ctx: dict[str, Any], member_name: str, enum_name: str = "") -> Any:
    return getattr(_resolve_enum(ctx, enum_name), member_name)


@then(parsers.parse('"{enum_name}" 成员 {member} 的 value 是 {expected}'))
def then_member_value(enum_name: str, member: str, expected: str, bdd_context: dict[str, Any]) -> None:
    m = _member(bdd_context, member, enum_name)
    val: int | str = _try_int(expected.strip("'\""))
    assert m.value == val, f"value: 期望 {val!r}, 实际 {m.value!r}"


@then(parsers.parse('"{enum_name}" 成员 {member} 的 x_meta {attr} 是 {expected}'))
def then_xmeta_attr(enum_name: str, member: str, attr: str, expected: str, bdd_context: dict[str, Any]) -> None:
    m = _member(bdd_context, member, enum_name)
    actual = getattr(m.x_meta, attr)
    val: int | str = _try_int(expected.strip("'\""))
    assert actual == val, f"x_meta.{attr}: 期望 {val!r}, 实际 {actual!r}"


@then(parsers.parse('"{enum_name}" 成员 {member} 是 int 实例'))
def then_member_is_int(enum_name: str, member: str, bdd_context: dict[str, Any]) -> None:
    m = _member(bdd_context, member, enum_name)
    assert isinstance(m, int), f"期望 isinstance({m!r}, int)"


@then(parsers.parse('"{enum_name}" 成员 {member} 是自身枚举的实例'))
def then_member_is_own_instance(enum_name: str, member: str, bdd_context: dict[str, Any]) -> None:
    m = _member(bdd_context, member, enum_name)
    cls = _resolve_enum(bdd_context, enum_name)
    assert isinstance(m, cls), f"期望 isinstance({m!r}, {cls.__name__})"


@then(parsers.parse('通过值 {value} 实例化 "{enum_name}" 得到成员 {member}'))
def then_instantiation(value: str, enum_name: str, member: str, bdd_context: dict[str, Any]) -> None:
    cls = _resolve_enum(bdd_context, enum_name)
    try:
        val = int(value)
    except ValueError:
        val = value.strip("'\"")
    result = cls(val)
    expected = _member(bdd_context, member, enum_name)
    assert result is expected, f"期望 {cls.__name__}({val!r}) is {expected!r}, 实际 {result!r}"


@then(parsers.parse('"{enum_name}" 的成员总数是 {expected:d}'))
def then_member_count(enum_name: str, expected: int, bdd_context: dict[str, Any]) -> None:
    cls = _resolve_enum(bdd_context, enum_name)
    actual = len(list(cls))
    assert actual == expected, f"成员总数: 期望 {expected}, 实际 {actual}"


@then(parsers.parse('str 表示 "{enum_name}" 成员 {member} 是 {expected}'))
def then_str_value(enum_name: str, member: str, expected: str, bdd_context: dict[str, Any]) -> None:
    m = _member(bdd_context, member, enum_name)
    val = expected.strip("'\"")
    assert str(m) == val, f"str(): 期望 {val!r}, 实际 {str(m)!r}"


@then(parsers.parse('"{enum_name}" 的 to_db_field_comment 包含 {expected}'))
def then_db_comment_contains(enum_name: str, expected: str, bdd_context: dict[str, Any]) -> None:
    cls = _resolve_enum(bdd_context, enum_name)
    result = cls.to_db_field_comment()
    val = expected.strip("'\"")
    assert val in result, f"{val!r} 不在 {result!r} 中"


@then(parsers.parse('"{enum_name}" 的 to_db_field_comment 包含 {expected} 是假'))
def then_db_comment_not_contains(enum_name: str, expected: str, bdd_context: dict[str, Any]) -> None:
    cls = _resolve_enum(bdd_context, enum_name)
    result = cls.to_db_field_comment()
    val = expected.strip("'\"")
    assert val not in result, f"{val!r} 不应在 {result!r} 中"


@then(parsers.parse('之前定义的 "{enum_name}" 成员 {member} 的 x_meta {attr} 是 {expected}'))
def then_previous_enum_xmeta_attr(enum_name: str, member: str, attr: str, expected: str, bdd_context: dict[str, Any]) -> None:
    """跨场景断言 — 现已改为同场景内通过多 Given 步骤共享, 保留以备后用."""
    m = _member(bdd_context, member, enum_name)
    actual = getattr(m.x_meta, attr)
    val = expected.strip("'\"")
    assert actual == val, f"x_meta.{attr}: 期望 {val!r}, 实际 {actual!r}"


# ════════════════════════════════════════════════════════════════
# 场景注册
# ════════════════════════════════════════════════════════════════


# -- basic-usage.feature --


@scenario("enumx/basic-usage.feature", "继承 MetaInfoIntEnum 并访问基本属性")
def test_basic_int_enum() -> None: ...


@scenario("enumx/basic-usage.feature", "继承 MetaInfoStrEnum 并访问基本属性")
def test_basic_str_enum() -> None: ...


@scenario("enumx/basic-usage.feature", "to_db_field_comment 生成数据库注释")
def test_db_field_comment() -> None: ...


@scenario("enumx/basic-usage.feature", "to_db_field_comment 不包含其他枚举的描述")
def test_db_field_comment_false() -> None: ...


# -- extend-xmetainfo.feature --


@scenario("enumx/extend-xmetainfo.feature", "扩展 XMetaInfo 添加 color 和 order 字段")
def test_extend_xmetainfo_for_int_enum() -> None: ...


@scenario("enumx/extend-xmetainfo.feature", "扩展 XMetaInfo 用于 StrEnum 添加 icon 字段")
def test_extend_xmetainfo_for_str_enum() -> None: ...


# -- intermediate-base.feature --


@scenario("enumx/intermediate-base.feature", "通过中间基类统一扩展 XMetaInfo")
def test_intermediate_base() -> None: ...


@scenario("enumx/intermediate-base.feature", "多个业务枚举共享同一个中间基类")
def test_multiple_enums_share_intermediate_base() -> None: ...
