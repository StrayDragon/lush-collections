"""参考实现 conformance 验证 — 用内存 DAL 跑全套一致性测试.

此文件继承 conformance 套件, 注入 InMemory 参考实现的 fixture,
证明 conformance 测试本身的正确性, 同时为下游适配包提供写法示例.
"""

from __future__ import annotations

from typing import Any

import pytest

from lush_dal_protocol.testing.conformance import (
    AsyncFullDALConformanceTests,
    SyncFullDALConformanceTests,
)
from lush_dal_protocol.testing.reference import (
    InMemoryAsyncDAL,
    InMemoryCU,
    InMemorySession,
    InMemorySyncDAL,
)


class TestInMemorySyncConformance(SyncFullDALConformanceTests):
    """同步参考实现: 完整一致性套件验证."""

    @pytest.fixture
    def dal_class(self):
        return InMemorySyncDAL

    @pytest.fixture
    def session(self):
        return InMemorySession()

    @pytest.fixture
    def sample_cu(self):
        return InMemoryCU(name="ref-test")

    @pytest.fixture
    def make_cu(self):
        return lambda label: InMemoryCU(name=f"ref-{label}")

    @pytest.fixture
    def where_clause_factory(self):
        def _factory(entity: Any) -> list:
            name = entity.name
            return [lambda e, _n=name: e.name == _n]

        return _factory


class TestInMemoryAsyncConformance(AsyncFullDALConformanceTests):
    """异步参考实现: 完整一致性套件验证."""

    @pytest.fixture
    def dal_class(self):
        return InMemoryAsyncDAL

    @pytest.fixture
    def session(self):
        return InMemorySession()

    @pytest.fixture
    def sample_cu(self):
        return InMemoryCU(name="ref-test")

    @pytest.fixture
    def make_cu(self):
        return lambda label: InMemoryCU(name=f"ref-{label}")

    @pytest.fixture
    def where_clause_factory(self):
        def _factory(entity: Any) -> list:
            name = entity.name
            return [lambda e, _n=name: e.name == _n]

        return _factory
