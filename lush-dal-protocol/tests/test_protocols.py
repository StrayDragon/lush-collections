"""ABC 模块测试.

验证分层 ABC 的结构完整性: 不可直接实例化, 子类必须实现全部 abstractmethod.
"""

import pytest

from lush_dal_protocol.abc import (
    AbstractAsyncBaseDAL,
    AbstractAsyncReadDAL,
    AbstractAsyncWriteDAL,
    AbstractSyncBaseDAL,
    AbstractSyncReadDAL,
    AbstractSyncWriteDAL,
)

ALL_ABCS = [
    AbstractSyncReadDAL,
    AbstractSyncWriteDAL,
    AbstractSyncBaseDAL,
    AbstractAsyncReadDAL,
    AbstractAsyncWriteDAL,
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
}


class TestABCMethodCompleteness:
    @pytest.mark.parametrize(
        "abc_cls,layer",
        [
            (AbstractSyncReadDAL, "read"),
            (AbstractSyncWriteDAL, "write"),
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
