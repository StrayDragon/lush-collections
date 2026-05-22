"""DAL 一致性验证测试套件.

提供可复用的测试 mixin 类, 下游 ORM 适配包继承后注入 fixture 即可验证 ABC 实现.

使用方式::

    from lush_dal_protocol.testing import SyncBaseDALConformanceTests


    class TestMyDAL(SyncBaseDALConformanceTests):
        @pytest.fixture
        def dal_class(self):
            return MyConcreteDAL

        @pytest.fixture
        def session(self): ...

        @pytest.fixture
        def sample_cu(self):
            return MyCU(name="test")
"""

from __future__ import annotations

from typing import Any


class SyncReadDALConformanceTests:
    """同步 Read DAL 一致性测试."""

    def _get_entity_id(self, entity: Any, field: str = "id") -> int:
        return getattr(entity, field)

    def test_get_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        found = dal_class.get_by_id(session, eid)
        assert found is not None

    def test_get_by_id_nonexistent(self, dal_class: Any, session: Any) -> None:
        result = dal_class.get_by_id(session, 999999)
        assert result is None

    def test_ret_dto_after_get_by_id(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        dto = dal_class.ret_dto_after_get_by_id(session, eid)
        assert dto is not None

    def test_ret_dto_after_get_by_id_nonexistent(self, dal_class: Any, session: Any) -> None:
        result = dal_class.ret_dto_after_get_by_id(session, 999999)
        assert result is None

    def test_get_all_default_pagination(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        dal_class.create(session, sample_cu)
        result = dal_class.get_all(session)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_get_all_with_pagination(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        dal_class.create(session, sample_cu)
        dal_class.create(session, sample_cu)
        page1 = dal_class.get_all(session, skip=0, limit=1)
        assert len(page1) == 1

    def test_count_returns_int(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        initial = dal_class.count(session)
        assert isinstance(initial, int)
        assert initial >= 0
        dal_class.create(session, sample_cu)
        after = dal_class.count(session)
        assert after == initial + 1

    def test_exists_true_for_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        assert dal_class.exists(session, eid) is True

    def test_exists_false_for_nonexistent(self, dal_class: Any, session: Any) -> None:
        assert dal_class.exists(session, 999999) is False

    def test_batch_get_id__entity(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        e1 = dal_class.create(session, sample_cu)
        e2 = dal_class.create(session, sample_cu)
        eid1, eid2 = self._get_entity_id(e1), self._get_entity_id(e2)
        result = dal_class.batch_get_id__entity(session, [eid1, eid2, 999999])
        assert eid1 in result
        assert eid2 in result
        assert 999999 not in result

    def test_batch_get_id__dto(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        e1 = dal_class.create(session, sample_cu)
        eid1 = self._get_entity_id(e1)
        result = dal_class.batch_get_id__dto(session, [eid1])
        assert eid1 in result

    def test_iter_record_dtos_yields(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        dal_class.create(session, sample_cu)
        records = list(dal_class.iter_record_dtos(session, batch_size=10))
        assert len(records) >= 1


class SyncWriteDALConformanceTests:
    """同步 Write DAL 一致性测试."""

    def _get_entity_id(self, entity: Any, field: str = "id") -> int:
        return getattr(entity, field)

    def test_create_returns_entity(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        assert entity is not None
        assert hasattr(entity, "id")

    def test_create_no_refresh(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu, need_refresh=False)
        assert entity is not None

    def test_ret_dto_after_create(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        dto = dal_class.ret_dto_after_create(session, sample_cu)
        assert dto is not None

    def test_update_only_set_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        updated = dal_class.update_only_set_by_id(session, eid, sample_cu)
        assert updated is not None

    def test_update_only_set_by_id_nonexistent(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        result = dal_class.update_only_set_by_id(session, 999999, sample_cu)
        assert result is None

    def test_ret_dto_after_update_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        dto = dal_class.ret_dto_after_update_by_id(session, eid, sample_cu)
        assert dto is not None

    def test_ret_dto_after_update_by_id_nonexistent(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        result = dal_class.ret_dto_after_update_by_id(session, 999999, sample_cu)
        assert result is None

    def test_delete_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        assert dal_class.delete_by_id(session, eid) is True

    def test_delete_by_id_nonexistent(self, dal_class: Any, session: Any) -> None:
        assert dal_class.delete_by_id(session, 999999) is False

    def test_delete_then_get_returns_none(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        dal_class.delete_by_id(session, eid)
        session.expire_all()
        result = dal_class.get_by_id(session, eid)
        assert result is None


class SyncBaseDALConformanceTests(SyncReadDALConformanceTests, SyncWriteDALConformanceTests):
    """同步完整 CRUD DAL 一致性测试 (Read + Write)."""


class AsyncReadDALConformanceTests:
    """异步 Read DAL 一致性测试."""

    def _get_entity_id(self, entity: Any, field: str = "id") -> int:
        return getattr(entity, field)

    async def test_get_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        found = await dal_class.get_by_id(session, eid)
        assert found is not None

    async def test_get_by_id_nonexistent(self, dal_class: Any, session: Any) -> None:
        result = await dal_class.get_by_id(session, 999999)
        assert result is None

    async def test_ret_dto_after_get_by_id(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        dto = await dal_class.ret_dto_after_get_by_id(session, eid)
        assert dto is not None

    async def test_ret_dto_after_get_by_id_nonexistent(self, dal_class: Any, session: Any) -> None:
        result = await dal_class.ret_dto_after_get_by_id(session, 999999)
        assert result is None

    async def test_get_all_default_pagination(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        await dal_class.create(session, sample_cu)
        result = await dal_class.get_all(session)
        assert isinstance(result, list)
        assert len(result) >= 1

    async def test_get_all_with_pagination(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        await dal_class.create(session, sample_cu)
        await dal_class.create(session, sample_cu)
        page1 = await dal_class.get_all(session, skip=0, limit=1)
        assert len(page1) == 1

    async def test_count_returns_int(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        initial = await dal_class.count(session)
        assert isinstance(initial, int)
        await dal_class.create(session, sample_cu)
        after = await dal_class.count(session)
        assert after == initial + 1

    async def test_exists_true_for_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        assert await dal_class.exists(session, eid) is True

    async def test_exists_false_for_nonexistent(self, dal_class: Any, session: Any) -> None:
        assert await dal_class.exists(session, 999999) is False

    async def test_batch_get_id__entity(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        e1 = await dal_class.create(session, sample_cu)
        eid1 = self._get_entity_id(e1)
        result = await dal_class.batch_get_id__entity(session, [eid1, 999999])
        assert eid1 in result
        assert 999999 not in result

    async def test_batch_get_id__dto(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        e1 = await dal_class.create(session, sample_cu)
        eid1 = self._get_entity_id(e1)
        result = await dal_class.batch_get_id__dto(session, [eid1])
        assert eid1 in result

    async def test_iter_record_dtos_yields(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        await dal_class.create(session, sample_cu)
        records = [dto async for dto in dal_class.iter_record_dtos(session, batch_size=10)]
        assert len(records) >= 1


class AsyncWriteDALConformanceTests:
    """异步 Write DAL 一致性测试."""

    def _get_entity_id(self, entity: Any, field: str = "id") -> int:
        return getattr(entity, field)

    async def test_create_returns_entity(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        assert entity is not None
        assert hasattr(entity, "id")

    async def test_create_no_refresh(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu, need_refresh=False)
        assert entity is not None

    async def test_ret_dto_after_create(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        dto = await dal_class.ret_dto_after_create(session, sample_cu)
        assert dto is not None

    async def test_update_only_set_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        updated = await dal_class.update_only_set_by_id(session, eid, sample_cu)
        assert updated is not None

    async def test_update_only_set_by_id_nonexistent(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        result = await dal_class.update_only_set_by_id(session, 999999, sample_cu)
        assert result is None

    async def test_ret_dto_after_update_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        dto = await dal_class.ret_dto_after_update_by_id(session, eid, sample_cu)
        assert dto is not None

    async def test_ret_dto_after_update_by_id_nonexistent(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        result = await dal_class.ret_dto_after_update_by_id(session, 999999, sample_cu)
        assert result is None

    async def test_delete_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        assert await dal_class.delete_by_id(session, eid) is True

    async def test_delete_by_id_nonexistent(self, dal_class: Any, session: Any) -> None:
        assert await dal_class.delete_by_id(session, 999999) is False

    async def test_delete_then_get_returns_none(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        await dal_class.delete_by_id(session, eid)
        session.expire_all()
        result = await dal_class.get_by_id(session, eid)
        assert result is None


class AsyncBaseDALConformanceTests(AsyncReadDALConformanceTests, AsyncWriteDALConformanceTests):
    """异步完整 CRUD DAL 一致性测试 (Read + Write)."""
