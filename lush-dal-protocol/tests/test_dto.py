"""dto 模块测试."""

import datetime
from typing import ClassVar

import pytest
from pydantic import ConfigDict

from lush_dal_protocol.dto import (
    EXTEND_TABLE_CU_CONFIG,
    BaseCU,
    BaseCUConfigDict,
    BaseDTO,
    StdBaseCU,
    StdBaseDTO,
    pk_field_cu_config,
)


class _FakeOrm:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _TestCU(BaseCU["_FakeOrm"]):
    _Table: ClassVar[type] = _FakeOrm
    name: str
    value: int = 0


class _TestCUWithFromAttr(_TestCU):
    model_config = ConfigDict(str_strip_whitespace=True, from_attributes=True)


class _TestDTO(BaseDTO["_TestCUWithFromAttr"]):
    _CU: ClassVar[type[_TestCUWithFromAttr]] = _TestCUWithFromAttr
    name: str
    value: int = 0
    model_config = ConfigDict(from_attributes=True)


class _StdCU(StdBaseCU["_FakeOrm"]):
    _Table: ClassVar[type] = _FakeOrm
    name: str


class _StdDTO(StdBaseDTO[_StdCU]):
    _CU: ClassVar[type[_StdCU]] = _StdCU
    name: str
    model_config = ConfigDict(from_attributes=True)


class TestBaseCU:
    def test_to_orm_model(self):
        cu = _TestCU(name="hello", value=42)
        orm = cu.to_orm_model()
        assert orm.name == "hello"
        assert orm.value == 42

    def test_to_orm_model_excludes_id(self):
        class _WithIdCU(BaseCU["_FakeOrm"]):
            _Table: ClassVar[type] = _FakeOrm
            id: int = 0
            name: str

        cu = _WithIdCU(id=999, name="test")
        orm = cu.to_orm_model()
        assert not hasattr(orm, "id")
        assert orm.name == "test"

    def test_strip_whitespace(self):
        cu = _TestCU(name="  hello  ")
        assert cu.name == "hello"

    def test_default_cu_config(self):
        cfg = _TestCU.resolve_cu_config()
        assert cfg["to_orm_exclude"] == frozenset({"id"})
        assert cfg["update_exclude"] == frozenset({"id"})
        assert isinstance(cfg["to_orm_exclude"], frozenset)

    def test_extend_table_keeps_id_on_to_orm(self):
        class _ExtendCU(BaseCU["_FakeOrm"]):
            _Table: ClassVar[type] = _FakeOrm
            cu_config = EXTEND_TABLE_CU_CONFIG
            id: int
            name: str

        cfg = _ExtendCU.resolve_cu_config()
        assert cfg["to_orm_exclude"] == frozenset()
        assert cfg["update_exclude"] == frozenset({"id"})

        cu = _ExtendCU(id=42, name="ext")
        orm = cu.to_orm_model()
        assert orm.id == 42
        assert orm.name == "ext"

    def test_partial_override_inherits_update_exclude(self):
        class _MidCU(BaseCU["_FakeOrm"]):
            _Table: ClassVar[type] = _FakeOrm
            cu_config = BaseCUConfigDict(to_orm_exclude=frozenset({"id", "secret"}))
            name: str

        class _ChildCU(_MidCU):
            cu_config = BaseCUConfigDict(to_orm_exclude=frozenset())

        child_cfg = _ChildCU.resolve_cu_config()
        assert child_cfg["to_orm_exclude"] == frozenset()
        assert child_cfg["update_exclude"] == frozenset({"id"})

        mid_cfg = _MidCU.resolve_cu_config()
        assert mid_cfg["to_orm_exclude"] == frozenset({"id", "secret"})
        assert mid_cfg["update_exclude"] == frozenset({"id"})

    def test_basecu_resolved_config_on_base_class(self):
        cfg = BaseCU.resolve_cu_config()
        assert cfg["to_orm_exclude"] == frozenset({"id"})
        assert cfg["update_exclude"] == frozenset({"id"})

    def test_empty_cu_config_dict_inherits_all_defaults(self):
        class _EmptyCfgCU(BaseCU["_FakeOrm"]):
            _Table: ClassVar[type] = _FakeOrm
            cu_config = BaseCUConfigDict()
            name: str

        cfg = _EmptyCfgCU.resolve_cu_config()
        assert cfg["to_orm_exclude"] == frozenset({"id"})
        assert cfg["update_exclude"] == frozenset({"id"})

    def test_override_update_exclude_only(self):
        class _UpdateOnlyCU(BaseCU["_FakeOrm"]):
            _Table: ClassVar[type] = _FakeOrm
            cu_config = BaseCUConfigDict(update_exclude=frozenset({"id", "locked"}))
            id: int = 0
            name: str
            locked: str = "x"

        cfg = _UpdateOnlyCU.resolve_cu_config()
        assert cfg["to_orm_exclude"] == frozenset({"id"})
        assert cfg["update_exclude"] == frozenset({"id", "locked"})
        orm = _UpdateOnlyCU(id=1, name="n", locked="y").to_orm_model()
        assert not hasattr(orm, "id")
        assert orm.name == "n"

    def test_three_level_mro_merge(self):
        class _L1(BaseCU["_FakeOrm"]):
            _Table: ClassVar[type] = _FakeOrm
            cu_config = BaseCUConfigDict(to_orm_exclude=frozenset({"id", "a"}))

        class _L2(_L1):
            cu_config = BaseCUConfigDict(update_exclude=frozenset({"id", "b"}))

        class _L3(_L2):
            cu_config = BaseCUConfigDict(to_orm_exclude=frozenset())
            name: str

        cfg = _L3.resolve_cu_config()
        assert cfg["to_orm_exclude"] == frozenset()
        assert cfg["update_exclude"] == frozenset({"id", "b"})

    def test_extend_constant_is_kwargs_typeddict(self):
        assert pk_field_cu_config("id", keep_on_create=True) == EXTEND_TABLE_CU_CONFIG
        assert EXTEND_TABLE_CU_CONFIG["to_orm_exclude"] == frozenset()
        assert EXTEND_TABLE_CU_CONFIG["update_exclude"] == frozenset({"id"})

    def test_pk_field_cu_config_defaults(self):
        cfg = pk_field_cu_config()
        assert cfg["to_orm_exclude"] == frozenset({"id"})
        assert cfg["update_exclude"] == frozenset({"id"})

    def test_pk_field_cu_config_custom_pk(self):
        cfg = pk_field_cu_config("user_id", keep_on_create=True)
        assert cfg["to_orm_exclude"] == frozenset()
        assert cfg["update_exclude"] == frozenset({"user_id"})

    def test_sqlalchemyx_style_basecu_inherits_protocol_config(self):
        """子类不声明 cu_config 时仍继承默认 exclude id."""

        class _Plain(BaseCU["_FakeOrm"]):
            _Table: ClassVar[type] = _FakeOrm
            id: int = 1
            name: str

        assert _Plain.resolve_cu_config()["to_orm_exclude"] == frozenset({"id"})
        assert not hasattr(_Plain(id=9, name="p").to_orm_model(), "id")


class TestBaseDTO:
    def test_to_cu(self):
        dto = _TestDTO(name="world", value=10)
        cu = dto.to_cu()
        assert isinstance(cu, _TestCUWithFromAttr)
        assert cu.name == "world"
        assert cu.value == 10

    def test_from_attributes(self):
        obj = _FakeOrm(name="attr", value=5)
        dto = _TestDTO.model_validate(obj)
        assert dto.name == "attr"
        assert dto.value == 5


class TestStdBaseCU:
    def test_default_fields(self):
        cu = _StdCU(name="std")
        assert cu.create_operator_id == 0
        assert cu.update_operator_id is None

    def test_deprecation_warning_on_subclass(self):
        with pytest.warns(DeprecationWarning, match="StdBaseCU"):

            class _NewStdCU(StdBaseCU["_FakeOrm"]):
                _Table: ClassVar[type] = _FakeOrm
                name: str


class TestStdBaseDTO:
    def test_standard_fields(self):
        now = datetime.datetime.now()
        dto = _StdDTO(
            id=1,
            name="std",
            create_datetime=now,
            create_operator_id=10,
            update_datetime=now,
            update_operator_id=20,
        )
        assert dto.id == 1
        assert dto.create_operator_id == 10

    def test_deprecation_warning_on_subclass(self):
        with pytest.warns(DeprecationWarning, match="StdBaseDTO"):

            class _NewStdDTO(StdBaseDTO[_StdCU]):
                _CU: ClassVar[type[_StdCU]] = _StdCU
                name: str
                model_config = ConfigDict(from_attributes=True)
