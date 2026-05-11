"""api_contracts 模块测试 — 验证一致性测试套件覆盖所有协议方法."""

import inspect

from lush_dal_protocol.protocols.api_contracts import (
    AsyncDALConformanceTests,
    SyncDALConformanceTests,
)
from lush_dal_protocol.protocols.dal import (
    AsyncBaseDALProtocol,
    SyncBaseDALProtocol,
)


def _protocol_public_methods(proto_cls: type) -> set[str]:
    """提取 Protocol 类链上声明的公开操作方法名."""
    skip_names = {"Protocol", "Generic", "object"}
    methods = set()
    for cls in proto_cls.__mro__:
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
    """验证同步一致性套件覆盖了全部协议方法."""

    def test_every_protocol_method_has_conformance_test(self):
        """SyncBaseDALProtocol 的每个方法都应有至少一个对应的一致性测试."""
        proto_methods = _protocol_public_methods(SyncBaseDALProtocol)
        test_names = _test_method_names(SyncDALConformanceTests)

        uncovered = []
        for method in sorted(proto_methods):
            if not any(method in t for t in test_names):
                uncovered.append(method)
        assert not uncovered, f"协议方法缺少一致性测试: {uncovered}"

    def test_suite_is_inheritable_as_mixin(self):
        """套件应可作为 mixin 被子类继承, 子类自动获得全部测试方法."""

        class _Sub(SyncDALConformanceTests):
            pass

        assert issubclass(_Sub, SyncDALConformanceTests)
        assert _test_method_names(_Sub) == _test_method_names(SyncDALConformanceTests)

    def test_all_test_methods_accept_fixture_params(self):
        """所有测试方法应为实例方法, 且至少接受 fixture 参数."""
        for name in _test_method_names(SyncDALConformanceTests):
            method = getattr(SyncDALConformanceTests, name)
            sig = inspect.signature(method)
            params = list(sig.parameters)
            assert "self" in params, f"{name} 应为实例方法"
            assert len(params) >= 2, f"{name} 应至少接受一个 fixture 参数"


class TestAsyncConformanceSuiteCoverage:
    """验证异步一致性套件覆盖了全部协议方法."""

    def test_every_protocol_method_has_conformance_test(self):
        """AsyncBaseDALProtocol 的每个方法都应有至少一个对应的一致性测试."""
        proto_methods = _protocol_public_methods(AsyncBaseDALProtocol)
        test_names = _test_method_names(AsyncDALConformanceTests)

        uncovered = []
        for method in sorted(proto_methods):
            if not any(method in t for t in test_names):
                uncovered.append(method)
        assert not uncovered, f"协议方法缺少一致性测试: {uncovered}"

    def test_suite_is_inheritable_as_mixin(self):
        """套件应可作为 mixin 被子类继承, 子类自动获得全部测试方法."""

        class _Sub(AsyncDALConformanceTests):
            pass

        assert issubclass(_Sub, AsyncDALConformanceTests)
        assert _test_method_names(_Sub) == _test_method_names(AsyncDALConformanceTests)

    def test_all_test_methods_are_coroutines(self):
        """异步套件的所有测试方法应为 async def (协程函数)."""
        for name in _test_method_names(AsyncDALConformanceTests):
            method = getattr(AsyncDALConformanceTests, name)
            assert inspect.iscoroutinefunction(method), f"{name} 应为 async def"
