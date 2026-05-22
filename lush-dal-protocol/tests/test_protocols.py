"""ABC 模块测试.

验证分层 ABC 的结构完整性: 不可直接实例化, 子类必须实现全部 abstractmethod.
"""

import pytest

from lush_dal_protocol.abc import (
    AbstractAsyncAdvancedWriteDAL,
    AbstractAsyncBaseDAL,
    AbstractAsyncBatchFieldDAL,
    AbstractAsyncLockDAL,
    AbstractAsyncRawSQLDAL,
    AbstractAsyncReadDAL,
    AbstractAsyncWriteDAL,
    AbstractSyncAdvancedWriteDAL,
    AbstractSyncBaseDAL,
    AbstractSyncBatchFieldDAL,
    AbstractSyncLockDAL,
    AbstractSyncRawSQLDAL,
    AbstractSyncReadDAL,
    AbstractSyncWriteDAL,
)
from lush_dal_protocol.params import Extra, ExtraT

ALL_ABCS = [
    AbstractSyncReadDAL,
    AbstractSyncWriteDAL,
    AbstractSyncLockDAL,
    AbstractSyncBatchFieldDAL,
    AbstractSyncAdvancedWriteDAL,
    AbstractSyncRawSQLDAL,
    AbstractSyncBaseDAL,
    AbstractAsyncReadDAL,
    AbstractAsyncWriteDAL,
    AbstractAsyncLockDAL,
    AbstractAsyncBatchFieldDAL,
    AbstractAsyncAdvancedWriteDAL,
    AbstractAsyncRawSQLDAL,
    AbstractAsyncBaseDAL,
]


class TestABCsNotInstantiable:
    @pytest.mark.parametrize("abc_cls", ALL_ABCS, ids=lambda c: c.__name__)
    def test_cannot_instantiate(self, abc_cls):
        with pytest.raises(TypeError):
            abc_cls()


EXPECTED_METHODS = {
    "read": {
        "get_by_id",
        "get_all",
        "count",
        "exists",
        "ret_dto_after_get_by_id",
        "batch_get_id__entity",
        "batch_get_id__dto",
        "iter_record_dtos",
    },
    "write": {"create", "ret_dto_after_create", "update_only_set_by_id", "ret_dto_after_update_by_id", "delete_by_id"},
    "lock": {"get_by_id_for_update", "batch_get_for_update", "get_one_for_update", "update_only_set_with_optimistic_lock"},
    "batch_field": {"batch_get_field__entity", "batch_get_field__dto"},
    "advanced_write": {"update_full_by_id", "update_partial_by_id", "batch_update_by_conditions", "batch_update_by_ids"},
    "raw_sql": {"execute_sql", "execute_readonly_sql"},
}


class TestABCMethodCompleteness:
    @pytest.mark.parametrize(
        "abc_cls,layer",
        [
            (AbstractSyncReadDAL, "read"),
            (AbstractSyncWriteDAL, "write"),
            (AbstractSyncLockDAL, "lock"),
            (AbstractSyncBatchFieldDAL, "batch_field"),
            (AbstractSyncAdvancedWriteDAL, "advanced_write"),
            (AbstractSyncRawSQLDAL, "raw_sql"),
        ],
        ids=lambda x: x if isinstance(x, str) else x.__name__,
    )
    def test_sync_abc_has_expected_methods(self, abc_cls, layer):
        expected = EXPECTED_METHODS[layer]
        actual = {name for name in vars(abc_cls) if not name.startswith("_")}
        assert expected == actual, f"Mismatch for {abc_cls.__name__}: missing={expected - actual}, extra={actual - expected}"

    @pytest.mark.parametrize(
        "abc_cls,layer",
        [
            (AbstractAsyncReadDAL, "read"),
            (AbstractAsyncWriteDAL, "write"),
            (AbstractAsyncLockDAL, "lock"),
            (AbstractAsyncBatchFieldDAL, "batch_field"),
            (AbstractAsyncAdvancedWriteDAL, "advanced_write"),
            (AbstractAsyncRawSQLDAL, "raw_sql"),
        ],
        ids=lambda x: x if isinstance(x, str) else x.__name__,
    )
    def test_async_abc_has_expected_methods(self, abc_cls, layer):
        expected = EXPECTED_METHODS[layer]
        actual = {name for name in vars(abc_cls) if not name.startswith("_")}
        assert expected == actual, f"Mismatch for {abc_cls.__name__}: missing={expected - actual}, extra={actual - expected}"

    def test_base_dal_combines_read_and_write(self):
        sync_methods = {name for name in dir(AbstractSyncBaseDAL) if not name.startswith("_")}
        expected = EXPECTED_METHODS["read"] | EXPECTED_METHODS["write"]
        assert expected.issubset(sync_methods)

        async_methods = {name for name in dir(AbstractAsyncBaseDAL) if not name.startswith("_")}
        assert expected.issubset(async_methods)


class TestExtraParams:
    def test_extra_defaults(self):
        extra = Extra()
        assert extra is not None

    def test_extra_frozen(self):
        extra = Extra()
        with pytest.raises(AttributeError):
            extra.x = 1

    def test_extra_subclassable(self):
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class MyExtra(Extra):
            lock_timeout: int | None = None
            need_refresh: bool = False

        ext = MyExtra(lock_timeout=5, need_refresh=True)
        assert ext.lock_timeout == 5
        assert ext.need_refresh is True
        assert isinstance(ext, Extra)

    def test_extra_typevar_importable(self):
        assert ExtraT is not None
