"""参考实现 conformance 验证 — 用内存 DAL 跑全套一致性测试.

此文件继承 conformance 套件, 注入 InMemory 参考实现的 fixture,
证明 conformance 测试本身的正确性, 同时为下游适配包提供写法示例.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from lush_dal_protocol.dto import EXTEND_TABLE_CU_CONFIG
from lush_dal_protocol.testing.conformance import (
    AsyncBaseDALConformanceTests,
    SyncBaseDALConformanceTests,
)
from lush_dal_protocol.testing.reference import (
    InMemoryAsyncDAL,
    InMemoryCU,
    InMemoryEntity,
    InMemorySession,
    InMemorySyncDAL,
)


class TestInMemorySyncConformance(SyncBaseDALConformanceTests):
    """同步参考实现: Base (Read + Write) 一致性套件验证."""

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


class TestInMemoryAsyncConformance(AsyncBaseDALConformanceTests):
    """异步参考实现: Base (Read + Write) 一致性套件验证."""

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


class _ExtendInMemoryCU(InMemoryCU):
    """共享主键 / 客户端指定 id 的 CU."""

    _Table: ClassVar[type] = InMemoryEntity
    cu_config = EXTEND_TABLE_CU_CONFIG
    id: int | None = None
    name: str = ""


class TestInMemoryClientPrimaryKey:
    """InMemorySession: create dump 含 id 时采用客户端主键."""

    def test_create_keeps_client_id(self):
        session = InMemorySession()
        entity = InMemorySyncDAL.create(session, _ExtendInMemoryCU(id=42, name="ext"))
        assert entity.id == 42
        assert InMemorySyncDAL.get_by_id(session, 42) is not None
        # 后续自增从 max+1 起
        auto = InMemorySyncDAL.create(session, InMemoryCU(name="auto"))
        assert auto.id == 43

    def test_duplicate_client_id_raises(self):
        session = InMemorySession()
        InMemorySyncDAL.create(session, _ExtendInMemoryCU(id=7, name="a"))
        with pytest.raises(ValueError, match="duplicate id: 7"):
            InMemorySyncDAL.create(session, _ExtendInMemoryCU(id=7, name="b"))

    def test_auto_increment_when_id_absent(self):
        session = InMemorySession()
        e1 = InMemorySyncDAL.create(session, InMemoryCU(name="a"))
        e2 = InMemorySyncDAL.create(session, InMemoryCU(name="b"))
        assert e1.id == 1
        assert e2.id == 2
