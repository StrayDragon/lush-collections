"""DAL 一致性验证测试套件.

提供可复用的测试 mixin 类, 下游 ORM 适配包可以继承这些测试类
并注入具体的 session、DAL、CU、DTO 来验证实现是否符合 ``lush-dalx`` 协议约定.

使用方式::

    from lush_dalx.testing import SyncDALConformanceTests

    class TestMySQLAlchemyDAL(SyncDALConformanceTests):
        @pytest.fixture
        def dal_class(self):
            return MyConcreteDAL

        @pytest.fixture
        def session(self):
            # 返回你的 ORM session
            ...

        @pytest.fixture
        def sample_cu(self):
            # 返回一个有效的 CU 实例
            return MyCU(name="test")

        @pytest.fixture
        def entity_id_field(self):
            return "id"
"""

from __future__ import annotations

from typing import Any


class SyncDALConformanceTests:
    """同步 DAL 一致性验证测试套件.

    下游实现继承此类并通过 pytest fixture 注入:
    - ``dal_class``: DAL 类 (应实现 SyncBaseDALProtocol)
    - ``session``: 数据库会话
    - ``sample_cu``: 有效的 CU 实例
    - ``entity_id_field``: 实体主键字段名, 默认 "id"
    """

    def _get_entity_id(self, entity: Any, field: str = "id") -> int:
        return getattr(entity, field)

    def test_create_returns_entity(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """create() 应返回具有有效 ID 的 ORM 实体."""
        entity = dal_class.create(session, sample_cu)
        assert entity is not None
        assert hasattr(entity, "id")

    def test_create_no_refresh(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """create(need_refresh=False) 应返回实体但不执行 refresh."""
        entity = dal_class.create(session, sample_cu, need_refresh=False)
        assert entity is not None

    def test_get_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """get_by_id() 对已存在的实体应返回非 None."""
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        found = dal_class.get_by_id(session, eid)
        assert found is not None

    def test_get_by_id_nonexistent(self, dal_class: Any, session: Any) -> None:
        """get_by_id() 对不存在的 ID 应返回 None."""
        result = dal_class.get_by_id(session, 999999)
        assert result is None

    def test_ret_dto_after_get_by_id(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """ret_dto_after_get_by_id() 应返回 DTO 对象."""
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        dto = dal_class.ret_dto_after_get_by_id(session, eid)
        assert dto is not None

    def test_ret_dto_after_get_by_id_nonexistent(self, dal_class: Any, session: Any) -> None:
        """ret_dto_after_get_by_id() 对不存在的 ID 应返回 None."""
        result = dal_class.ret_dto_after_get_by_id(session, 999999)
        assert result is None

    def test_get_all_default_pagination(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """get_all() 默认参数应返回列表."""
        dal_class.create(session, sample_cu)
        result = dal_class.get_all(session)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_get_all_with_pagination(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """get_all(skip, limit) 应正确分页."""
        dal_class.create(session, sample_cu)
        dal_class.create(session, sample_cu)
        page1 = dal_class.get_all(session, skip=0, limit=1)
        assert len(page1) == 1

    def test_count_returns_int(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """count() 应返回非负整数."""
        initial = dal_class.count(session)
        assert isinstance(initial, int)
        assert initial >= 0

        dal_class.create(session, sample_cu)
        after = dal_class.count(session)
        assert after == initial + 1

    def test_exists_true_for_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """exists() 对已存在的 ID 应返回 True."""
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        assert dal_class.exists(session, eid) is True

    def test_exists_false_for_nonexistent(self, dal_class: Any, session: Any) -> None:
        """exists() 对不存在的 ID 应返回 False."""
        assert dal_class.exists(session, 999999) is False

    def test_batch_get_id__entity(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """batch_get_id__entity() 应返回 {id: entity} 字典."""
        e1 = dal_class.create(session, sample_cu)
        e2 = dal_class.create(session, sample_cu)
        eid1, eid2 = self._get_entity_id(e1), self._get_entity_id(e2)

        result = dal_class.batch_get_id__entity(session, [eid1, eid2, 999999])
        assert eid1 in result
        assert eid2 in result
        assert 999999 not in result

    def test_batch_get_id__dto(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """batch_get_id__dto() 应返回 {id: DTO} 字典."""
        e1 = dal_class.create(session, sample_cu)
        eid1 = self._get_entity_id(e1)

        result = dal_class.batch_get_id__dto(session, [eid1])
        assert eid1 in result

    def test_ret_dto_after_create(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """ret_dto_after_create() 应返回 DTO 对象."""
        dto = dal_class.ret_dto_after_create(session, sample_cu)
        assert dto is not None

    def test_update_only_set_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """update_only_set_by_id() 对已存在的实体应返回更新后的实体."""
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        updated = dal_class.update_only_set_by_id(session, eid, sample_cu)
        assert updated is not None

    def test_update_only_set_by_id_nonexistent(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """update_only_set_by_id() 对不存在的 ID 应返回 None."""
        result = dal_class.update_only_set_by_id(session, 999999, sample_cu)
        assert result is None

    def test_delete_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """delete_by_id() 对已存在的实体应返回 True."""
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        assert dal_class.delete_by_id(session, eid) is True

    def test_delete_by_id_nonexistent(self, dal_class: Any, session: Any) -> None:
        """delete_by_id() 对不存在的 ID 应返回 False."""
        assert dal_class.delete_by_id(session, 999999) is False

    def test_delete_then_get_returns_none(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """删除后再 get_by_id 应返回 None (验证软删除/物理删除生效)."""
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        dal_class.delete_by_id(session, eid)
        session.expire_all()
        result = dal_class.get_by_id(session, eid)
        assert result is None

    def test_iter_record_dtos_yields(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """iter_record_dtos() 应以迭代器方式返回 DTO."""
        dal_class.create(session, sample_cu)
        records = list(dal_class.iter_record_dtos(session, batch_size=10))
        assert len(records) >= 1


class AsyncDALConformanceTests:
    """异步 DAL 一致性验证测试套件.

    下游实现继承此类并通过 pytest fixture 注入:
    - ``dal_class``: DAL 类 (应实现 AsyncBaseDALProtocol)
    - ``session``: 异步数据库会话
    - ``sample_cu``: 有效的 CU 实例
    - ``entity_id_field``: 实体主键字段名, 默认 "id"
    """

    def _get_entity_id(self, entity: Any, field: str = "id") -> int:
        return getattr(entity, field)

    async def test_create_returns_entity(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """create() 应返回具有有效 ID 的 ORM 实体."""
        entity = await dal_class.create(session, sample_cu)
        assert entity is not None
        assert hasattr(entity, "id")

    async def test_create_no_refresh(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """create(need_refresh=False) 应返回实体但不执行 refresh."""
        entity = await dal_class.create(session, sample_cu, need_refresh=False)
        assert entity is not None

    async def test_get_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """get_by_id() 对已存在的实体应返回非 None."""
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        found = await dal_class.get_by_id(session, eid)
        assert found is not None

    async def test_get_by_id_nonexistent(self, dal_class: Any, session: Any) -> None:
        """get_by_id() 对不存在的 ID 应返回 None."""
        result = await dal_class.get_by_id(session, 999999)
        assert result is None

    async def test_ret_dto_after_get_by_id(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """ret_dto_after_get_by_id() 应返回 DTO 对象."""
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        dto = await dal_class.ret_dto_after_get_by_id(session, eid)
        assert dto is not None

    async def test_ret_dto_after_get_by_id_nonexistent(self, dal_class: Any, session: Any) -> None:
        """ret_dto_after_get_by_id() 对不存在的 ID 应返回 None."""
        result = await dal_class.ret_dto_after_get_by_id(session, 999999)
        assert result is None

    async def test_get_all_default_pagination(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """get_all() 默认参数应返回列表."""
        await dal_class.create(session, sample_cu)
        result = await dal_class.get_all(session)
        assert isinstance(result, list)
        assert len(result) >= 1

    async def test_count_returns_int(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """count() 应返回非负整数."""
        initial = await dal_class.count(session)
        assert isinstance(initial, int)
        await dal_class.create(session, sample_cu)
        after = await dal_class.count(session)
        assert after == initial + 1

    async def test_exists_true_for_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """exists() 对已存在的 ID 应返回 True."""
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        assert await dal_class.exists(session, eid) is True

    async def test_exists_false_for_nonexistent(self, dal_class: Any, session: Any) -> None:
        """exists() 对不存在的 ID 应返回 False."""
        assert await dal_class.exists(session, 999999) is False

    async def test_batch_get_id__entity(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """batch_get_id__entity() 应返回 {id: entity} 字典."""
        e1 = await dal_class.create(session, sample_cu)
        eid1 = self._get_entity_id(e1)
        result = await dal_class.batch_get_id__entity(session, [eid1, 999999])
        assert eid1 in result
        assert 999999 not in result

    async def test_batch_get_id__dto(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """batch_get_id__dto() 应返回 {id: DTO} 字典."""
        e1 = await dal_class.create(session, sample_cu)
        eid1 = self._get_entity_id(e1)
        result = await dal_class.batch_get_id__dto(session, [eid1])
        assert eid1 in result

    async def test_ret_dto_after_create(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """ret_dto_after_create() 应返回 DTO 对象."""
        dto = await dal_class.ret_dto_after_create(session, sample_cu)
        assert dto is not None

    async def test_update_only_set_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """update_only_set_by_id() 对已存在的实体应返回更新后的实体."""
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        updated = await dal_class.update_only_set_by_id(session, eid, sample_cu)
        assert updated is not None

    async def test_update_only_set_by_id_nonexistent(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """update_only_set_by_id() 对不存在的 ID 应返回 None."""
        result = await dal_class.update_only_set_by_id(session, 999999, sample_cu)
        assert result is None

    async def test_delete_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """delete_by_id() 对已存在的实体应返回 True."""
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        assert await dal_class.delete_by_id(session, eid) is True

    async def test_delete_by_id_nonexistent(self, dal_class: Any, session: Any) -> None:
        """delete_by_id() 对不存在的 ID 应返回 False."""
        assert await dal_class.delete_by_id(session, 999999) is False
