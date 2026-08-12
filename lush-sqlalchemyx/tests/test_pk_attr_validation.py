"""``validate_orm_dal_pk_config`` / ``_pk_attr`` 成对配置校验."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa
from pydantic import ConfigDict
from sqlalchemy.orm import Mapped, mapped_column

from lush_sqlalchemyx.base.dal import (
    BaseCU,
    BaseDTO,
    BasicSyncBaseTable,
    SyncBaseDAL,
    SyncReadDAL,
    pk_field_cu_config,
    validate_orm_dal_pk_config,
)
from lush_sqlalchemyx.base.dal._common import _table_pk_attr_names


class _IdPkTable(BasicSyncBaseTable):
    __tablename__ = "pk_val_id_table"
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(50), nullable=False)


class _UserPkTable(BasicSyncBaseTable):
    __tablename__ = "pk_val_user_table"
    user_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(50), nullable=False)


class _UserPkCU(BaseCU["_UserPkTable"]):
    _Table: ClassVar[type[_UserPkTable]] = _UserPkTable
    cu_config = pk_field_cu_config("user_id")
    user_id: int | None = None
    name: str


class _UserPkDTO(BaseDTO[_UserPkCU]):
    _CU: ClassVar[type[_UserPkCU]] = _UserPkCU
    user_id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class _DefaultIdCU(BaseCU["_IdPkTable"]):
    _Table: ClassVar[type[_IdPkTable]] = _IdPkTable
    name: str


class _DefaultIdDTO(BaseDTO[_DefaultIdCU]):
    _CU: ClassVar[type[_DefaultIdCU]] = _DefaultIdCU
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class _MismatchedExcludeCU(BaseCU["_UserPkTable"]):
    """仍按默认 exclude id, 未对齐 user_id."""

    _Table: ClassVar[type[_UserPkTable]] = _UserPkTable
    user_id: int | None = None
    name: str


def test_validate_skips_without_table() -> None:
    class _Bare:
        _pk_attr = "id"

    validate_orm_dal_pk_config(_Bare)


def test_validate_skips_abstract_without_tablename() -> None:
    class _AbsDAL:
        _Table = BasicSyncBaseTable
        _pk_attr = "id"

    validate_orm_dal_pk_config(_AbsDAL)


def test_validate_rejects_empty_pk_attr() -> None:
    class _Bad:
        _Table = _IdPkTable
        _pk_attr = ""

    with pytest.raises(TypeError, match="_pk_attr 必须为非空 str"):
        validate_orm_dal_pk_config(_Bad)


def test_validate_rejects_missing_column() -> None:
    class _Bad:
        _Table = _IdPkTable
        _pk_attr = "missing_pk"

    with pytest.raises(TypeError, match="不包含主键字段"):
        validate_orm_dal_pk_config(_Bad)


def test_validate_rejects_pk_attr_not_in_mapper_pk() -> None:
    class _Bad:
        _Table = _UserPkTable
        _pk_attr = "name"  # 列存在但不是主键

    with pytest.raises(TypeError, match="不在表 .* 的主键属性"):
        validate_orm_dal_pk_config(_Bad)


def test_validate_rejects_cu_update_exclude_mismatch() -> None:
    class _Bad:
        _Table = _UserPkTable
        _CU = _MismatchedExcludeCU
        _pk_attr = "user_id"

    with pytest.raises(TypeError, match="update_exclude"):
        validate_orm_dal_pk_config(_Bad)


def test_subclass_creation_rejects_mismatched_cu() -> None:
    with pytest.raises(TypeError, match="update_exclude"):

        class _BadDAL(SyncBaseDAL[_UserPkTable, _UserPkDTO, _MismatchedExcludeCU]):
            _Table = _UserPkTable
            _DTO = _UserPkDTO
            _CU = _MismatchedExcludeCU
            _pk_attr = "user_id"


def test_subclass_creation_accepts_aligned_custom_pk() -> None:
    class _OkDAL(SyncBaseDAL[_UserPkTable, _UserPkDTO, _UserPkCU]):
        _Table = _UserPkTable
        _DTO = _UserPkDTO
        _CU = _UserPkCU
        _pk_attr = "user_id"

    assert _OkDAL._pk_attr == "user_id"


def test_subclass_creation_accepts_default_id() -> None:
    class _OkDAL(SyncBaseDAL[_IdPkTable, _DefaultIdDTO, _DefaultIdCU]):
        _Table = _IdPkTable
        _DTO = _DefaultIdDTO
        _CU = _DefaultIdCU

    assert _OkDAL._pk_attr == "id"


def test_read_dal_without_cu_still_checks_table_pk() -> None:
    class _OkRead(SyncReadDAL[_UserPkTable, _UserPkDTO]):
        _Table = _UserPkTable
        _DTO = _UserPkDTO
        _pk_attr = "user_id"

    assert _OkRead._pk_attr == "user_id"

    with pytest.raises(TypeError, match="不在表"):

        class _BadRead(SyncReadDAL[_UserPkTable, _UserPkDTO]):
            _Table = _UserPkTable
            _DTO = _UserPkDTO
            _pk_attr = "name"


def test_validate_skips_cu_without_resolve_cu_config() -> None:
    class _PlainCU:
        pass

    class _Ok:
        _Table = _IdPkTable
        _CU = _PlainCU
        _pk_attr = "id"

    validate_orm_dal_pk_config(_Ok)


def test_validate_skips_when_update_exclude_missing() -> None:
    class _Cu:
        @classmethod
        def resolve_cu_config(cls) -> dict[str, Any]:
            return {}

    class _Ok:
        _Table = _IdPkTable
        _CU = _Cu
        _pk_attr = "id"

    validate_orm_dal_pk_config(_Ok)


def test_validate_skips_when_resolve_returns_non_dict() -> None:
    class _Cu:
        @classmethod
        def resolve_cu_config(cls) -> Any:
            return ("not", "a", "dict")

    class _Ok:
        _Table = _IdPkTable
        _CU = _Cu
        _pk_attr = "id"

    validate_orm_dal_pk_config(_Ok)


def test_table_pk_attr_names_happy_path() -> None:
    assert _table_pk_attr_names(_UserPkTable) == frozenset({"user_id"})
    assert _table_pk_attr_names(_IdPkTable) == frozenset({"id"})


def test_table_pk_attr_names_no_inspection() -> None:
    assert _table_pk_attr_names(object) is None  # type: ignore[arg-type]


def test_table_pk_attr_names_empty_primary_key() -> None:
    mapper = MagicMock()
    mapper.primary_key = ()
    with patch("sqlalchemy.inspect", return_value=mapper):
        assert _table_pk_attr_names(_IdPkTable) == frozenset()


def test_table_pk_attr_names_mapper_none() -> None:
    with patch("sqlalchemy.inspect", return_value=None):
        assert _table_pk_attr_names(_IdPkTable) is None


def test_table_pk_attr_names_primary_key_attr_error() -> None:
    class _BrokenMapper:
        @property
        def primary_key(self) -> Any:
            raise AttributeError("x")

    with patch("sqlalchemy.inspect", return_value=_BrokenMapper()):
        assert _table_pk_attr_names(_IdPkTable) is None


def test_table_pk_attr_names_primary_key_type_error() -> None:
    class _BrokenMapper:
        @property
        def primary_key(self) -> Any:
            raise TypeError("x")

    with patch("sqlalchemy.inspect", return_value=_BrokenMapper()):
        assert _table_pk_attr_names(_IdPkTable) is None


def test_table_pk_attr_names_fallback_column_key() -> None:
    col = MagicMock()
    col.key = "fallback_pk"
    col.name = "fallback_pk"
    mapper = MagicMock()
    mapper.primary_key = (col,)
    mapper.get_property_by_column.side_effect = KeyError("missing")
    with patch("sqlalchemy.inspect", return_value=mapper):
        assert _table_pk_attr_names(_IdPkTable) == frozenset({"fallback_pk"})


def test_table_pk_attr_names_fallback_none_key() -> None:
    col = MagicMock(spec=[])  # no key/name
    mapper = MagicMock()
    mapper.primary_key = (col,)
    mapper.get_property_by_column.side_effect = ValueError("missing")
    with patch("sqlalchemy.inspect", return_value=mapper):
        assert _table_pk_attr_names(_IdPkTable) == frozenset()


def test_table_pk_attr_names_inspect_type_error() -> None:
    with patch("sqlalchemy.inspect", side_effect=TypeError("boom")):
        assert _table_pk_attr_names(_IdPkTable) is None


def test_validate_rejects_non_str_pk_attr() -> None:
    class _Bad:
        _Table = _IdPkTable
        _pk_attr = 123  # type: ignore[assignment]

    with pytest.raises(TypeError, match="_pk_attr 必须为非空 str"):
        validate_orm_dal_pk_config(_Bad)
