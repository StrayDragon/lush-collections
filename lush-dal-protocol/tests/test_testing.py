"""testing 模块测试 — 验证一致性测试套件覆盖所有 ABC 方法."""

import inspect

from lush_dal_protocol.abc import AbstractAsyncBaseDAL, AbstractSyncBaseDAL
from lush_dal_protocol.testing.conformance import (
    AsyncAdvancedWriteDALConformanceTests,
    AsyncBaseDALConformanceTests,
    AsyncFullDALConformanceTests,
    AsyncLockDALConformanceTests,
    AsyncReadDALConformanceTests,
    AsyncWriteDALConformanceTests,
    SyncAdvancedWriteDALConformanceTests,
    SyncBaseDALConformanceTests,
    SyncFullDALConformanceTests,
    SyncLockDALConformanceTests,
    SyncReadDALConformanceTests,
    SyncWriteDALConformanceTests,
)


def _abc_public_methods(abc_cls: type) -> set[str]:
    """提取 ABC 类链上声明的公开操作方法名."""
    skip_names = {"ABC", "Generic", "object"}
    methods = set()
    for cls in abc_cls.__mro__:
        if cls.__name__ in skip_names:
            continue
        for name in vars(cls):
            if name.startswith("_"):
                continue
            obj = vars(cls)[name]
            if isinstance(obj, (classmethod, staticmethod)) or inspect.isfunction(obj):
                methods.add(name)
    return methods


def _test_method_names(suite_cls: type) -> set[str]:
    return {m for m in dir(suite_cls) if m.startswith("test_")}


class TestSyncConformanceSuiteCoverage:
    def test_every_abc_method_has_conformance_test(self):
        abc_methods = _abc_public_methods(AbstractSyncBaseDAL)
        test_names = _test_method_names(SyncBaseDALConformanceTests)
        uncovered = []
        for method in sorted(abc_methods):
            if not any(method in t for t in test_names):
                uncovered.append(method)
        assert not uncovered, f"ABC 方法缺少一致性测试: {uncovered}"

    def test_suite_is_inheritable_as_mixin(self):
        class _Sub(SyncBaseDALConformanceTests):
            pass

        assert issubclass(_Sub, SyncBaseDALConformanceTests)
        assert _test_method_names(_Sub) == _test_method_names(SyncBaseDALConformanceTests)

    def test_all_test_methods_accept_fixture_params(self):
        for name in _test_method_names(SyncBaseDALConformanceTests):
            method = getattr(SyncBaseDALConformanceTests, name)
            sig = inspect.signature(method)
            params = list(sig.parameters)
            assert "self" in params, f"{name} 应为实例方法"
            assert len(params) >= 2, f"{name} 应至少接受一个 fixture 参数"

    def test_read_suite_is_subset_of_base(self):
        read_tests = _test_method_names(SyncReadDALConformanceTests)
        base_tests = _test_method_names(SyncBaseDALConformanceTests)
        assert read_tests.issubset(base_tests)

    def test_write_suite_is_subset_of_base(self):
        write_tests = _test_method_names(SyncWriteDALConformanceTests)
        base_tests = _test_method_names(SyncBaseDALConformanceTests)
        assert write_tests.issubset(base_tests)

    def test_lock_suite_has_tests(self):
        tests = _test_method_names(SyncLockDALConformanceTests)
        assert len(tests) >= 4

    def test_advanced_write_suite_has_tests(self):
        tests = _test_method_names(SyncAdvancedWriteDALConformanceTests)
        assert len(tests) >= 4

    def test_full_suite_is_superset_of_base(self):
        base_tests = _test_method_names(SyncBaseDALConformanceTests)
        full_tests = _test_method_names(SyncFullDALConformanceTests)
        assert base_tests.issubset(full_tests)
        assert len(full_tests) > len(base_tests)


class TestAsyncConformanceSuiteCoverage:
    def test_every_abc_method_has_conformance_test(self):
        abc_methods = _abc_public_methods(AbstractAsyncBaseDAL)
        test_names = _test_method_names(AsyncBaseDALConformanceTests)
        uncovered = []
        for method in sorted(abc_methods):
            if not any(method in t for t in test_names):
                uncovered.append(method)
        assert not uncovered, f"ABC 方法缺少一致性测试: {uncovered}"

    def test_suite_is_inheritable_as_mixin(self):
        class _Sub(AsyncBaseDALConformanceTests):
            pass

        assert issubclass(_Sub, AsyncBaseDALConformanceTests)
        assert _test_method_names(_Sub) == _test_method_names(AsyncBaseDALConformanceTests)

    def test_all_test_methods_are_coroutines(self):
        for name in _test_method_names(AsyncBaseDALConformanceTests):
            method = getattr(AsyncBaseDALConformanceTests, name)
            assert inspect.iscoroutinefunction(method), f"{name} 应为 async def"

    def test_read_suite_is_subset_of_base(self):
        read_tests = _test_method_names(AsyncReadDALConformanceTests)
        base_tests = _test_method_names(AsyncBaseDALConformanceTests)
        assert read_tests.issubset(base_tests)

    def test_write_suite_is_subset_of_base(self):
        write_tests = _test_method_names(AsyncWriteDALConformanceTests)
        base_tests = _test_method_names(AsyncBaseDALConformanceTests)
        assert write_tests.issubset(base_tests)

    def test_lock_suite_has_tests(self):
        tests = _test_method_names(AsyncLockDALConformanceTests)
        assert len(tests) >= 4

    def test_advanced_write_suite_has_tests(self):
        tests = _test_method_names(AsyncAdvancedWriteDALConformanceTests)
        assert len(tests) >= 4

    def test_full_suite_is_superset_of_base(self):
        base_tests = _test_method_names(AsyncBaseDALConformanceTests)
        full_tests = _test_method_names(AsyncFullDALConformanceTests)
        assert base_tests.issubset(full_tests)
        assert len(full_tests) > len(base_tests)

    def test_all_lock_methods_are_coroutines(self):
        for name in _test_method_names(AsyncLockDALConformanceTests):
            method = getattr(AsyncLockDALConformanceTests, name)
            assert inspect.iscoroutinefunction(method), f"{name} 应为 async def"

    def test_all_advanced_write_methods_are_coroutines(self):
        for name in _test_method_names(AsyncAdvancedWriteDALConformanceTests):
            method = getattr(AsyncAdvancedWriteDALConformanceTests, name)
            assert inspect.iscoroutinefunction(method), f"{name} 应为 async def"
