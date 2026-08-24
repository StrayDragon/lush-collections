"""纯 Python 原语的属性测试 (docs/design/11 §4).

适用判定: 无 IO、能陈述不变量的既有原语. 全部挂 ``property`` 标记,
不在 mysql matrix 中重复执行.
"""

from __future__ import annotations

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st
from lush_dal_protocol import BaseCUConfigDict, pk_field_cu_config
from pydantic import BaseModel, Field

from lush_sqlalchemyx.base.dal._common import _apply_none_policy, escape_like
from lush_sqlalchemyx.base.dal._dynamic import DynamicTableConfig, TableRef
from lush_sqlalchemyx.base.dal._pagination import decode_cursor, encode_cursor

pytestmark = pytest.mark.property

# ---------------------------------------------------------------------------
# cursor 编解码往返 (pagination)
# ---------------------------------------------------------------------------


@given(st.integers(min_value=-(2**63), max_value=2**63 - 1))
def test_property__cursor_roundtrip_int(pk: int) -> None:
    """任意 int 主键经 encode→decode 后得到原值的字符串形式."""
    assert decode_cursor(encode_cursor(pk)) == str(pk)


@given(
    value=st.text(
        alphabet=st.characters(blacklist_characters="\x00\r\n", blacklist_categories=("Cs",)),
        max_size=64,
    )
)
def test_property__cursor_roundtrip_text(value: str) -> None:
    """任意可 UTF-8 编码文本经 encode→decode 保持往返恒定 (代理字符不在合法域内)."""
    assert decode_cursor(encode_cursor(value)) == value


# ---------------------------------------------------------------------------
# escape_like: 转义完备性 + 语义往返
# ---------------------------------------------------------------------------

_LIKE_META = re.compile(r"(?<!\\)[%_]")  # 未被反斜杠转义的 % 或 _


@given(
    st.text(alphabet=st.characters(blacklist_characters="\x00"), max_size=32),
    st.sampled_from(["\\", "!", "#"]),
)
def test_property__escape_like_no_unescaped_meta(value: str, escape_char: str) -> None:
    """反斜杠转义时, 结果中不存在未转义的 % 与 _."""
    escaped, e = escape_like(value, escape_char)
    if escape_char == "\\":
        assert _LIKE_META.search(escaped) is None


@given(
    st.text(alphabet=st.characters(blacklist_characters="\x00"), max_size=32),
    st.sampled_from(["\\", "!"]),
)
def test_property__escape_like_roundtrip(value: str, escape_char: str) -> None:
    """按 LIKE 语义反转义 (先以占位符处理双转义) 应还原原始输入."""
    escaped, e = escape_like(value, escape_char)
    placeholder = "\x00"
    unescaped = escaped.replace(e + e, placeholder).replace(e + "%", "%").replace(e + "_", "_").replace(placeholder, e)
    assert unescaped == value


# ---------------------------------------------------------------------------
# pk_field_cu_config: 配置生成不变量
# ---------------------------------------------------------------------------


@given(st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]{0,31}", fullmatch=True))
def test_property__pk_field_cu_config_invariants(pk_field: str) -> None:
    """update_exclude 恒含主键; keep_on_create 决定 to_orm_exclude 是否排除主键."""
    cfg_default = pk_field_cu_config(pk_field)
    cfg_keep = pk_field_cu_config(pk_field, keep_on_create=True)
    for cfg in (cfg_default, cfg_keep):
        assert set(cfg.keys()) == {"to_orm_exclude", "update_exclude"}
        assert cfg["update_exclude"] == frozenset({pk_field})
    assert cfg_default["to_orm_exclude"] == frozenset({pk_field})
    assert cfg_keep["to_orm_exclude"] == frozenset()


@given(st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]{0,15}", fullmatch=True))
def test_property__base_cu_config_dict_partial_construct(pk_field: str) -> None:
    """BaseCUConfigDict 是 total=False 的 TypedDict, 允许部分键构造 (读取须 .get)."""
    partial: BaseCUConfigDict = BaseCUConfigDict(to_orm_exclude=frozenset({pk_field}))
    assert partial.get("to_orm_exclude") == frozenset({pk_field})


# ---------------------------------------------------------------------------
# NonePolicy 判定真值性质 (_common.py)
# ---------------------------------------------------------------------------


@given(st.integers(), st.sampled_from(["ignore", "allow", "forbid"]))
def test_property__none_policy_non_none_always_writes(value: int, policy: str) -> None:
    """非 None 值在任何策略下都应写入."""
    assert _apply_none_policy("col", value, none_policy=policy) is True


@given(st.sampled_from(["ignore", "allow", "forbid"]))
def test_property__none_policy_none_matrix(policy: str) -> None:
    """显式 None 的三策略判定矩阵: ignore 跳过 / allow 写入 / forbid 抛错."""
    if policy == "ignore":
        assert _apply_none_policy("col", None, none_policy=policy) is False
    elif policy == "allow":
        assert _apply_none_policy("col", None, none_policy=policy) is True
    else:
        with pytest.raises(ValueError, match="不允许置空"):
            _ = _apply_none_policy("col", None, none_policy=policy)


# ---------------------------------------------------------------------------
# TableRef 映射一致性 (Dynamic 路径的地基)
# ---------------------------------------------------------------------------


class _RowDTO(BaseModel):
    """列名与字段名一致的极简 DTO."""

    row_id: int = Field(alias="row_id")
    user_name: str | None = Field(default=None, alias="user_name")
    amount_cents: int = Field(default=0, alias="amount_cents")


_REF = TableRef.of("t_property_rows", _RowDTO)

_FIELD_NAMES = ("row_id", "user_name", "amount_cents")


@given(
    st.dictionaries(
        keys=st.sampled_from(_FIELD_NAMES),
        values=st.one_of(st.integers(min_value=0), st.none(), st.text(max_size=16)),
        max_size=3,
    ).filter(lambda d: isinstance(d.get("row_id"), int))
)
def test_property__table_ref_map_keys_exact(cu_data: dict[str, object]) -> None:
    """map_to_row_data 输出键集合 == 输入字段的 db 列名集合 (无多余、无遗漏)."""
    row = _REF.map_to_row_data(cu_data)
    assert set(row.keys()) == set(cu_data)


@given(st.booleans(), st.booleans())
def test_property__dynamic_table_config_frozen(exclude_pk: bool, readonly: bool) -> None:
    """配置对象 frozen+slots: 意外属性赋值立即 AttributeError (docs/design/11 §3)."""
    cfg = DynamicTableConfig(exclude_pk_on_create=exclude_pk, is_readonly=readonly)
    assert cfg.exclude_pk_on_create is exclude_pk
    with pytest.raises(AttributeError):
        cfg.is_readonly = True  # type: ignore[misc]
