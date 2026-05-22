"""dto 模块测试."""

import datetime
from typing import ClassVar

import pytest
from pydantic import ConfigDict

from lush_dal_protocol.dto import BaseCU, BaseDTO, StdBaseCU, StdBaseDTO


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
