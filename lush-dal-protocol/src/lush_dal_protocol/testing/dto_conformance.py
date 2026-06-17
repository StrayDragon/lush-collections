"""Dto* 协议一致性验证测试套件.

为 ``DtoSyncDAL`` / ``DtoAsyncDAL`` 提供可复用的测试 mixin.
与 ``Entity*`` conformance 不同:

- 实例方法 (非 classmethod)
- 仅覆盖 4 个核心方法: ``get_by_id``, ``create``, ``update_by_id``, ``delete_by_id``
- 无 ``EntityT``, 返回值直接是 DTO
- ``session`` 为 keyword arg (协议默认 ``NO_SESSION``, 测试中显式传入)

Fixture 协议
~~~~~~~~~~~~

必须提供::

    dal        — 被测 DAL 实例 (如 ``DynamicSyncDAL(table_ref, dto_class)``).
    session    — 数据库 session, 每个测试后自动回滚.
    sample_cu  — 用于创建实体的 CU 实例 (最简字段即可).

字段级隔离性测试额外需要::

    make_cu    — ``Callable[[str], CUModelT]``, 接收标签返回不同字段值的 CU.

下游实现指引::

    from lush_dal_protocol.testing import DtoSyncConformanceTests

    class TestMyDAL(DtoSyncConformanceTests):
        @pytest.fixture
        def dal(self, session): return MySyncDAL(...)

        @pytest.fixture
        def session(self): ...

        @pytest.fixture
        def sample_cu(self): return MyCU(name="test")

        @pytest.fixture
        def make_cu(self):
            return lambda label: MyCU(name=f"test-{label}")
"""

from __future__ import annotations

from typing import Any


class _DtoConformanceHelpers:
    """共享辅助方法."""

    def _get_dto_id(self, dto: Any) -> Any:
        """从 DTO 获取主键值."""
        return dto.id

    def _get_dto_label(self, dto: Any) -> Any:
        """尝试读取 DTO 的首个文本字段值, 用于字段级隔离性验证."""
        for field in ("name", "title", "label", "key"):
            val = getattr(dto, field, None)
            if val is not None:
                return val
        return None


# ===== Sync =====


class DtoSyncReadConformanceTests(_DtoConformanceHelpers):
    """同步 Dto* Read 一致性测试."""

    def test_get_by_id_existing(self, dal: Any, session: Any, sample_cu: Any) -> None:
        created = dal.create(sample_cu, session=session)
        eid = self._get_dto_id(created)
        found = dal.get_by_id(eid, session=session)
        assert found is not None
        assert self._get_dto_id(found) == eid

    def test_get_by_id_nonexistent(self, dal: Any, session: Any) -> None:
        assert dal.get_by_id(999999, session=session) is None

    def test_get_by_id_read_your_writes(self, dal: Any, session: Any, sample_cu: Any) -> None:
        """create 后立即 get_by_id, 必须返回同一条记录."""
        created = dal.create(sample_cu, session=session)
        eid = self._get_dto_id(created)
        found = dal.get_by_id(eid, session=session)
        assert found is not None
        assert self._get_dto_id(found) == eid


class DtoSyncWriteConformanceTests(_DtoConformanceHelpers):
    """同步 Dto* Write 一致性测试."""

    def test_create_returns_dto(self, dal: Any, session: Any, sample_cu: Any) -> None:
        created = dal.create(sample_cu, session=session)
        assert created is not None
        assert hasattr(created, "id")

    def test_create_unique_ids(self, dal: Any, session: Any, sample_cu: Any) -> None:
        """多次 create 返回互不相同的 id."""
        ids = {self._get_dto_id(dal.create(sample_cu, session=session)) for _ in range(5)}
        assert len(ids) == 5

    def test_update_by_id_existing(self, dal: Any, session: Any, sample_cu: Any) -> None:
        created = dal.create(sample_cu, session=session)
        eid = self._get_dto_id(created)
        affected = dal.update_by_id(eid, sample_cu, session=session)
        assert isinstance(affected, int)

    def test_update_by_id_nonexistent(self, dal: Any, session: Any, sample_cu: Any) -> None:
        affected = dal.update_by_id(999999, sample_cu, session=session)
        assert affected == 0

    def test_update_does_not_change_get_result(self, dal: Any, session: Any, sample_cu: Any) -> None:
        """update 后 get_by_id 仍能找到同一记录."""
        created = dal.create(sample_cu, session=session)
        eid = self._get_dto_id(created)
        dal.update_by_id(eid, sample_cu, session=session)
        found = dal.get_by_id(eid, session=session)
        assert found is not None
        assert self._get_dto_id(found) == eid

    def test_update_isolation(self, dal: Any, session: Any, sample_cu: Any) -> None:
        """update 不影响其他记录."""
        bystander = dal.create(sample_cu, session=session)
        target = dal.create(sample_cu, session=session)
        bystander_id = self._get_dto_id(bystander)
        dal.update_by_id(self._get_dto_id(target), sample_cu, session=session)
        assert dal.get_by_id(bystander_id, session=session) is not None

    def test_delete_by_id_existing(self, dal: Any, session: Any, sample_cu: Any) -> None:
        created = dal.create(sample_cu, session=session)
        assert dal.delete_by_id(self._get_dto_id(created), session=session) is True

    def test_delete_by_id_nonexistent(self, dal: Any, session: Any) -> None:
        assert dal.delete_by_id(999999, session=session) is False

    def test_delete_then_get_returns_none(self, dal: Any, session: Any, sample_cu: Any) -> None:
        created = dal.create(sample_cu, session=session)
        eid = self._get_dto_id(created)
        dal.delete_by_id(eid, session=session)
        assert dal.get_by_id(eid, session=session) is None

    def test_delete_idempotent(self, dal: Any, session: Any, sample_cu: Any) -> None:
        created = dal.create(sample_cu, session=session)
        eid = self._get_dto_id(created)
        assert dal.delete_by_id(eid, session=session) is True
        assert dal.delete_by_id(eid, session=session) is False

    def test_delete_isolation(self, dal: Any, session: Any, sample_cu: Any) -> None:
        """delete 不影响其他记录."""
        bystander = dal.create(sample_cu, session=session)
        target = dal.create(sample_cu, session=session)
        dal.delete_by_id(self._get_dto_id(target), session=session)
        assert dal.get_by_id(self._get_dto_id(bystander), session=session) is not None

    def test_mixed_ops_count_consistency(self, dal: Any, session: Any, sample_cu: Any) -> None:
        """create + delete 混合操作后, 被删记录不可见, 存活记录可查."""
        e1 = dal.create(sample_cu, session=session)
        e2 = dal.create(sample_cu, session=session)
        e3 = dal.create(sample_cu, session=session)
        dal.delete_by_id(self._get_dto_id(e1), session=session)
        assert dal.get_by_id(self._get_dto_id(e1), session=session) is None
        assert dal.get_by_id(self._get_dto_id(e2), session=session) is not None
        assert dal.get_by_id(self._get_dto_id(e3), session=session) is not None

    def test_create_then_delete_then_create(self, dal: Any, session: Any, sample_cu: Any) -> None:
        """create → delete → create 不冲突."""
        e1 = dal.create(sample_cu, session=session)
        dal.delete_by_id(self._get_dto_id(e1), session=session)
        e2 = dal.create(sample_cu, session=session)
        assert self._get_dto_id(e2) != self._get_dto_id(e1)


class DtoSyncFieldIsolationConformanceTests(_DtoConformanceHelpers):
    """同步字段级隔离性验证."""

    def test_create_preserves_field_value(self, dal: Any, session: Any, make_cu: Any) -> None:
        """create 后读回 DTO, 字段值与 CU 输入一致."""
        created = dal.create(make_cu("precise-value"), session=session)
        found = dal.get_by_id(self._get_dto_id(created), session=session)
        assert found is not None
        assert self._get_dto_label(found) == self._get_dto_label(created)

    def test_update_changes_only_target(self, dal: Any, session: Any, make_cu: Any) -> None:
        """update 后: 目标字段已更新, 旁观者字段不变."""
        bystander = dal.create(make_cu("bystander"), session=session)
        target = dal.create(make_cu("target"), session=session)
        bystander_label = self._get_dto_label(bystander)

        dal.update_by_id(self._get_dto_id(target), make_cu("changed"), session=session)
        bystander_after = dal.get_by_id(self._get_dto_id(bystander), session=session)
        assert bystander_after is not None
        assert self._get_dto_label(bystander_after) == bystander_label

    def test_delete_does_not_alter_bystander(self, dal: Any, session: Any, make_cu: Any) -> None:
        """delete 后: 旁观者字段值不变."""
        bystander = dal.create(make_cu("keeper"), session=session)
        target = dal.create(make_cu("disposable"), session=session)
        bystander_label = self._get_dto_label(bystander)

        dal.delete_by_id(self._get_dto_id(target), session=session)
        bystander_after = dal.get_by_id(self._get_dto_id(bystander), session=session)
        assert bystander_after is not None
        assert self._get_dto_label(bystander_after) == bystander_label

    def test_multiple_creates_preserve_distinct_values(self, dal: Any, session: Any, make_cu: Any) -> None:
        """批量创建后, 每个实体保持自己的字段值."""
        labels = ["first", "second", "third"]
        dtos = [dal.create(make_cu(lab), session=session) for lab in labels]
        snapshots = [(self._get_dto_id(d), self._get_dto_label(d)) for d in dtos]

        for did, label in snapshots:
            found = dal.get_by_id(did, session=session)
            assert found is not None
            assert self._get_dto_label(found) == label

    def test_update_actually_changes_value(self, dal: Any, session: Any, make_cu: Any) -> None:
        """update 后目标字段值确实发生了变更."""
        created = dal.create(make_cu("original"), session=session)
        eid = self._get_dto_id(created)
        original_label = self._get_dto_label(created)

        dal.update_by_id(eid, make_cu("modified"), session=session)
        updated = dal.get_by_id(eid, session=session)
        assert updated is not None
        assert self._get_dto_label(updated) != original_label


# ===== Sync Composed =====


class DtoSyncConformanceTests(
    DtoSyncReadConformanceTests,
    DtoSyncWriteConformanceTests,
):
    """同步 Dto* CRUD 一致性测试 (Read + Write)."""


class DtoSyncFullConformanceTests(
    DtoSyncReadConformanceTests,
    DtoSyncWriteConformanceTests,
    DtoSyncFieldIsolationConformanceTests,
):
    """同步 Dto* 完整一致性测试 (Read + Write + FieldIsolation)."""


# ===== Async =====


class DtoAsyncReadConformanceTests(_DtoConformanceHelpers):
    """异步 Dto* Read 一致性测试."""

    async def test_get_by_id_existing(self, dal: Any, session: Any, sample_cu: Any) -> None:
        created = await dal.create(sample_cu, session=session)
        eid = self._get_dto_id(created)
        found = await dal.get_by_id(eid, session=session)
        assert found is not None
        assert self._get_dto_id(found) == eid

    async def test_get_by_id_nonexistent(self, dal: Any, session: Any) -> None:
        assert await dal.get_by_id(999999, session=session) is None

    async def test_get_by_id_read_your_writes(self, dal: Any, session: Any, sample_cu: Any) -> None:
        created = await dal.create(sample_cu, session=session)
        eid = self._get_dto_id(created)
        found = await dal.get_by_id(eid, session=session)
        assert found is not None
        assert self._get_dto_id(found) == eid


class DtoAsyncWriteConformanceTests(_DtoConformanceHelpers):
    """异步 Dto* Write 一致性测试."""

    async def test_create_returns_dto(self, dal: Any, session: Any, sample_cu: Any) -> None:
        created = await dal.create(sample_cu, session=session)
        assert created is not None
        assert hasattr(created, "id")

    async def test_create_unique_ids(self, dal: Any, session: Any, sample_cu: Any) -> None:
        ids: set[int] = set()
        for _ in range(5):
            created = await dal.create(sample_cu, session=session)
            ids.add(self._get_dto_id(created))
        assert len(ids) == 5

    async def test_update_by_id_existing(self, dal: Any, session: Any, sample_cu: Any) -> None:
        created = await dal.create(sample_cu, session=session)
        eid = self._get_dto_id(created)
        affected = await dal.update_by_id(eid, sample_cu, session=session)
        assert isinstance(affected, int)

    async def test_update_by_id_nonexistent(self, dal: Any, session: Any, sample_cu: Any) -> None:
        affected = await dal.update_by_id(999999, sample_cu, session=session)
        assert affected == 0

    async def test_update_does_not_change_get_result(self, dal: Any, session: Any, sample_cu: Any) -> None:
        created = await dal.create(sample_cu, session=session)
        eid = self._get_dto_id(created)
        await dal.update_by_id(eid, sample_cu, session=session)
        found = await dal.get_by_id(eid, session=session)
        assert found is not None
        assert self._get_dto_id(found) == eid

    async def test_update_isolation(self, dal: Any, session: Any, sample_cu: Any) -> None:
        bystander = await dal.create(sample_cu, session=session)
        target = await dal.create(sample_cu, session=session)
        bystander_id = self._get_dto_id(bystander)
        await dal.update_by_id(self._get_dto_id(target), sample_cu, session=session)
        assert await dal.get_by_id(bystander_id, session=session) is not None

    async def test_delete_by_id_existing(self, dal: Any, session: Any, sample_cu: Any) -> None:
        created = await dal.create(sample_cu, session=session)
        assert await dal.delete_by_id(self._get_dto_id(created), session=session) is True

    async def test_delete_by_id_nonexistent(self, dal: Any, session: Any) -> None:
        assert await dal.delete_by_id(999999, session=session) is False

    async def test_delete_then_get_returns_none(self, dal: Any, session: Any, sample_cu: Any) -> None:
        created = await dal.create(sample_cu, session=session)
        eid = self._get_dto_id(created)
        await dal.delete_by_id(eid, session=session)
        assert await dal.get_by_id(eid, session=session) is None

    async def test_delete_idempotent(self, dal: Any, session: Any, sample_cu: Any) -> None:
        created = await dal.create(sample_cu, session=session)
        eid = self._get_dto_id(created)
        assert await dal.delete_by_id(eid, session=session) is True
        assert await dal.delete_by_id(eid, session=session) is False

    async def test_delete_isolation(self, dal: Any, session: Any, sample_cu: Any) -> None:
        bystander = await dal.create(sample_cu, session=session)
        target = await dal.create(sample_cu, session=session)
        await dal.delete_by_id(self._get_dto_id(target), session=session)
        assert await dal.get_by_id(self._get_dto_id(bystander), session=session) is not None

    async def test_mixed_ops_count_consistency(self, dal: Any, session: Any, sample_cu: Any) -> None:
        e1 = await dal.create(sample_cu, session=session)
        e2 = await dal.create(sample_cu, session=session)
        e3 = await dal.create(sample_cu, session=session)
        await dal.delete_by_id(self._get_dto_id(e1), session=session)
        assert await dal.get_by_id(self._get_dto_id(e1), session=session) is None
        assert await dal.get_by_id(self._get_dto_id(e2), session=session) is not None
        assert await dal.get_by_id(self._get_dto_id(e3), session=session) is not None

    async def test_create_then_delete_then_create(self, dal: Any, session: Any, sample_cu: Any) -> None:
        e1 = await dal.create(sample_cu, session=session)
        await dal.delete_by_id(self._get_dto_id(e1), session=session)
        e2 = await dal.create(sample_cu, session=session)
        assert self._get_dto_id(e2) != self._get_dto_id(e1)


class DtoAsyncFieldIsolationConformanceTests(_DtoConformanceHelpers):
    """异步字段级隔离性验证."""

    async def test_create_preserves_field_value(self, dal: Any, session: Any, make_cu: Any) -> None:
        created = await dal.create(make_cu("precise-value"), session=session)
        found = await dal.get_by_id(self._get_dto_id(created), session=session)
        assert found is not None
        assert self._get_dto_label(found) == self._get_dto_label(created)

    async def test_update_changes_only_target(self, dal: Any, session: Any, make_cu: Any) -> None:
        bystander = await dal.create(make_cu("bystander"), session=session)
        target = await dal.create(make_cu("target"), session=session)
        bystander_label = self._get_dto_label(bystander)

        await dal.update_by_id(self._get_dto_id(target), make_cu("changed"), session=session)
        bystander_after = await dal.get_by_id(self._get_dto_id(bystander), session=session)
        assert bystander_after is not None
        assert self._get_dto_label(bystander_after) == bystander_label

    async def test_delete_does_not_alter_bystander(self, dal: Any, session: Any, make_cu: Any) -> None:
        bystander = await dal.create(make_cu("keeper"), session=session)
        target = await dal.create(make_cu("disposable"), session=session)
        bystander_label = self._get_dto_label(bystander)

        await dal.delete_by_id(self._get_dto_id(target), session=session)
        bystander_after = await dal.get_by_id(self._get_dto_id(bystander), session=session)
        assert bystander_after is not None
        assert self._get_dto_label(bystander_after) == bystander_label

    async def test_multiple_creates_preserve_distinct_values(self, dal: Any, session: Any, make_cu: Any) -> None:
        labels = ["first", "second", "third"]
        dtos = [await dal.create(make_cu(lab), session=session) for lab in labels]
        snapshots = [(self._get_dto_id(d), self._get_dto_label(d)) for d in dtos]

        for did, label in snapshots:
            found = await dal.get_by_id(did, session=session)
            assert found is not None
            assert self._get_dto_label(found) == label

    async def test_update_actually_changes_value(self, dal: Any, session: Any, make_cu: Any) -> None:
        created = await dal.create(make_cu("original"), session=session)
        eid = self._get_dto_id(created)
        original_label = self._get_dto_label(created)

        await dal.update_by_id(eid, make_cu("modified"), session=session)
        updated = await dal.get_by_id(eid, session=session)
        assert updated is not None
        assert self._get_dto_label(updated) != original_label


# ===== Async Composed =====


class DtoAsyncConformanceTests(
    DtoAsyncReadConformanceTests,
    DtoAsyncWriteConformanceTests,
):
    """异步 Dto* CRUD 一致性测试 (Read + Write)."""


class DtoAsyncFullConformanceTests(
    DtoAsyncReadConformanceTests,
    DtoAsyncWriteConformanceTests,
    DtoAsyncFieldIsolationConformanceTests,
):
    """异步 Dto* 完整一致性测试 (Read + Write + FieldIsolation)."""
