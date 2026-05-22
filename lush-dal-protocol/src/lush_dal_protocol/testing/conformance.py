"""DAL 一致性验证测试套件.

提供可复用的测试 mixin 类, 下游 ORM 适配包继承后注入 fixture 即可验证 ABC 实现.

参考实现
~~~~~~~~

``lush_dal_protocol.testing.reference`` 模块提供了基于纯 Python 字典的内存参考实现
(``InMemorySyncDAL`` / ``InMemoryAsyncDAL``), 在本包内部跑完整 conformance 套件,
证明测试本身的正确性, 同时为下游提供每个 ABC 方法的预期语义示例.

Fixture 协议
~~~~~~~~~~~~

必须提供::

    dal_class   — 被测 DAL 类 (classmethod 风格).
    session     — 数据库 session, 每个测试后自动回滚 (不会 commit).
    sample_cu   — 用于创建实体的 CU 实例 (最简字段即可).

Full 套件额外需要::

    make_cu     — ``Callable[[str], CU]``, 接收区分标签返回不同字段值的 CU.
                  用于字段级隔离性验证. 例::

                      @pytest.fixture
                      def make_cu(self):
                          return lambda label: MyCU(name=f"test-{label}")

    where_clause_factory — (Lock 层) ``Callable[[entity], list]``, 返回匹配该实体的过滤条件.

下游实现指引
~~~~~~~~~~~~

1. ``session`` 必须使用 ORM 原生方式创建 (如 SQLAlchemy 的 ``AsyncSession``), 并配置
   事务回滚 (``begin`` / ``rollback``), 确保测试之间互不干扰.

2. ``make_cu("alpha")`` 和 ``make_cu("beta")`` 创建的实体必须有可区分的字段值.
   套件通过 ``_get_entity_label(entity)`` 读取实体的首个文本字段 (``name`` / ``title``)
   来验证字段级隔离性. 如果实体字段名不是 ``name``/``title``, 子类需覆写此方法.

3. ``where_clause_factory`` 应返回 ORM 原生过滤条件列表 (如 SQLAlchemy 的
   ``[Table.name == entity.name]``), 不能依赖 id.

4. 如需在写操作后刷新 session 缓存, 覆写 ``_post_write_refresh(self, session)``::

       def _post_write_refresh(self, session):
           session.expire_all()   # SQLAlchemy 示例

5. 参考 ``lush_dal_protocol.testing.reference`` 模块的写法和
   ``tests/test_reference_conformance.py`` 中的 fixture 注入方式.

使用方式::

    from lush_dal_protocol.testing import AsyncFullDALConformanceTests

    class TestMyDAL(AsyncFullDALConformanceTests):
        @pytest.fixture
        def dal_class(self): return MyDAL

        @pytest.fixture
        async def session(self, engine):
            async with AsyncSession(engine) as s:
                async with s.begin():
                    yield s

        @pytest.fixture
        def sample_cu(self): return MyCU(name="test")

        @pytest.fixture
        def make_cu(self):
            return lambda label: MyCU(name=f"test-{label}")

        @pytest.fixture
        def where_clause_factory(self):
            return lambda entity: [MyTable.name == entity.name]
"""

from __future__ import annotations

from typing import Any

import pytest

from lush_dal_protocol.errors import DBRetryableError


class _ConformanceHelpers:
    """共享辅助方法."""

    def _get_entity_id(self, entity: Any, field: str = "id") -> int:
        return getattr(entity, field)

    def _get_entity_label(self, entity: Any) -> Any:
        """尝试读取实体的首个文本字段值.

        下游如果字段名不是 name/title, 需覆写此方法.
        """
        for field in ("name", "title", "label", "key"):
            val = getattr(entity, field, None)
            if val is not None:
                return val
        return None

    def _get_entity_version(self, entity: Any) -> int:
        """读取实体版本号.

        默认读取 ``entity.version``. 下游如果字段名不同, 需覆写.
        """
        return getattr(entity, "version", 1)

    def _make_update_data(self, field: str, value: Any) -> Any:
        """构造批量更新数据.

        默认返回 ``{field: value}`` 字典.
        下游 ORM 包如需不同格式, 覆写此方法.
        """
        return {field: value}

    def _get_retryable_error_class(self) -> type[Exception]:
        """返回乐观锁冲突时的异常类型.

        默认返回 ``lush_dal_protocol.errors.DBRetryableError``.
        下游如使用自有异常类 (如 ``lush_sqlalchemyx`` 的 ``DBRetryableError``),
        覆写此方法::

            def _get_retryable_error_class(self):
                from lush_sqlalchemyx.base.dal._common import DBRetryableError

                return DBRetryableError
        """
        return DBRetryableError

    def _post_write_refresh(self, session: Any) -> None:
        """写操作后的 session 刷新钩子.

        默认 no-op. 下游覆写此方法以实现 ORM 特有的刷新逻辑,
        确保后续读操作返回最新数据::

            def _post_write_refresh(self, session):
                session.expire_all()  # SQLAlchemy 示例
        """


# ===== Sync =====


class SyncReadDALConformanceTests(_ConformanceHelpers):
    """同步 Read DAL 一致性测试."""

    def test_get_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        found = dal_class.get_by_id(session, eid)
        assert found is not None
        assert self._get_entity_id(found) == eid

    def test_get_by_id_nonexistent(self, dal_class: Any, session: Any) -> None:
        assert dal_class.get_by_id(session, 999999) is None

    def test_ret_dto_after_get_by_id(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        dto = dal_class.ret_dto_after_get_by_id(session, eid)
        assert dto is not None
        assert hasattr(dto, "id")

    def test_ret_dto_after_get_by_id_nonexistent(self, dal_class: Any, session: Any) -> None:
        assert dal_class.ret_dto_after_get_by_id(session, 999999) is None

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

    def test_get_all_returns_exact_count(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        initial_count = dal_class.count(session)
        dal_class.create(session, sample_cu)
        dal_class.create(session, sample_cu)
        all_records = dal_class.get_all(session, skip=0, limit=9999)
        assert len(all_records) == initial_count + 2

    def test_count_returns_int(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        initial = dal_class.count(session)
        assert isinstance(initial, int)
        assert initial >= 0
        dal_class.create(session, sample_cu)
        assert dal_class.count(session) == initial + 1

    def test_exists_true_for_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        assert dal_class.exists(session, self._get_entity_id(entity)) is True

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

    def test_get_all_skip_beyond_total(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        dal_class.create(session, sample_cu)
        total = dal_class.count(session)
        result = dal_class.get_all(session, skip=total + 100, limit=10)
        assert result == []

    def test_batch_get_with_empty_list(self, dal_class: Any, session: Any) -> None:
        assert dal_class.batch_get_id__entity(session, []) == {}
        assert dal_class.batch_get_id__dto(session, []) == {}

    def test_get_by_id_read_your_writes(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """create 后立即 get_by_id, 必须返回同一条记录."""
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        found = dal_class.get_by_id(session, eid)
        assert found is not None
        assert self._get_entity_id(found) == eid

    def test_count_zero_on_empty(self, dal_class: Any, session: Any) -> None:
        initial = dal_class.count(session)
        assert isinstance(initial, int)
        assert initial >= 0

    def test_exists_consistency_with_get_by_id(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        assert dal_class.exists(session, eid) == (dal_class.get_by_id(session, eid) is not None)
        assert not dal_class.exists(session, 999999)
        assert dal_class.get_by_id(session, 999999) is None

    def test_get_all_pagination_no_overlap(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """分页结果之间不应有 id 重叠."""
        for _ in range(3):
            dal_class.create(session, sample_cu)
        page1 = dal_class.get_all(session, skip=0, limit=2)
        page2 = dal_class.get_all(session, skip=2, limit=2)
        ids1 = {dto.id for dto in page1}
        ids2 = {dto.id for dto in page2}
        assert ids1.isdisjoint(ids2)

    def test_iter_count_matches_count(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """iter_record_dtos 总数应与 count() 一致."""
        dal_class.create(session, sample_cu)
        dal_class.create(session, sample_cu)
        count = dal_class.count(session)
        iter_count = len(list(dal_class.iter_record_dtos(session)))
        assert iter_count == count

    def test_batch_get_deduplicates(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """batch_get 传入重复 id 时, 结果集 key 不重复."""
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        result = dal_class.batch_get_id__entity(session, [eid, eid, eid])
        assert len(result) == 1
        assert eid in result


class SyncWriteDALConformanceTests(_ConformanceHelpers):
    """同步 Write DAL 一致性测试."""

    def test_create_returns_entity(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        assert entity is not None
        assert hasattr(entity, "id")

    def test_create_increments_count(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        before = dal_class.count(session)
        dal_class.create(session, sample_cu)
        assert dal_class.count(session) == before + 1

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
        assert self._get_entity_id(updated) == eid

    def test_update_only_set_by_id_nonexistent(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        assert dal_class.update_only_set_by_id(session, 999999, sample_cu) is None

    def test_update_does_not_change_count(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        dal_class.create(session, sample_cu)
        entity = dal_class.create(session, sample_cu)
        count_before = dal_class.count(session)
        dal_class.update_only_set_by_id(session, self._get_entity_id(entity), sample_cu)
        assert dal_class.count(session) == count_before

    def test_update_isolation(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        bystander = dal_class.create(session, sample_cu)
        target = dal_class.create(session, sample_cu)
        bystander_id = self._get_entity_id(bystander)
        dal_class.update_only_set_by_id(session, self._get_entity_id(target), sample_cu)
        self._post_write_refresh(session)
        assert dal_class.get_by_id(session, bystander_id) is not None

    def test_ret_dto_after_update_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        dto = dal_class.ret_dto_after_update_by_id(session, self._get_entity_id(entity), sample_cu)
        assert dto is not None

    def test_ret_dto_after_update_by_id_nonexistent(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        assert dal_class.ret_dto_after_update_by_id(session, 999999, sample_cu) is None

    def test_delete_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        assert dal_class.delete_by_id(session, self._get_entity_id(entity)) is True

    def test_delete_by_id_nonexistent(self, dal_class: Any, session: Any) -> None:
        assert dal_class.delete_by_id(session, 999999) is False

    def test_delete_decrements_count(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        count_before = dal_class.count(session)
        dal_class.delete_by_id(session, self._get_entity_id(entity))
        assert dal_class.count(session) == count_before - 1

    def test_delete_isolation(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        bystander = dal_class.create(session, sample_cu)
        target = dal_class.create(session, sample_cu)
        dal_class.delete_by_id(session, self._get_entity_id(target))
        self._post_write_refresh(session)
        assert dal_class.get_by_id(session, self._get_entity_id(bystander)) is not None

    def test_delete_then_get_returns_none(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        dal_class.delete_by_id(session, eid)
        self._post_write_refresh(session)
        assert dal_class.get_by_id(session, eid) is None

    def test_delete_idempotent(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        assert dal_class.delete_by_id(session, eid) is True
        assert dal_class.delete_by_id(session, eid) is False

    def test_mixed_ops_count_accuracy(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """混合 create/delete 后, count 必须精确反映行数变化."""
        initial = dal_class.count(session)
        e1 = dal_class.create(session, sample_cu)
        dal_class.create(session, sample_cu)
        dal_class.create(session, sample_cu)
        dal_class.delete_by_id(session, self._get_entity_id(e1))
        assert dal_class.count(session) == initial + 2

    def test_update_preserves_id(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        updated = dal_class.update_only_set_by_id(session, eid, sample_cu)
        assert updated is not None
        assert self._get_entity_id(updated) == eid

    def test_exists_false_after_delete(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        assert dal_class.exists(session, eid) is True
        dal_class.delete_by_id(session, eid)
        self._post_write_refresh(session)
        assert dal_class.exists(session, eid) is False

    def test_dto_fields_match_entity(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """DTO 的 id 必须与 entity 的 id 一致."""
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        dto = dal_class.ret_dto_after_get_by_id(session, eid)
        assert dto is not None
        assert dto.id == eid

    def test_create_unique_ids(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """多次 create 返回互不相同的 id."""
        ids = {self._get_entity_id(dal_class.create(session, sample_cu)) for _ in range(5)}
        assert len(ids) == 5

    def test_ret_dto_after_create_id_findable(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """ret_dto_after_create 返回的 id 可通过 get_by_id 找回."""
        dto = dal_class.ret_dto_after_create(session, sample_cu)
        assert dal_class.get_by_id(session, dto.id) is not None


class SyncFieldIsolationDALConformanceTests(_ConformanceHelpers):
    """同步字段级隔离性验证.

    需要 ``make_cu`` fixture 创建可区分字段值的 CU.
    通过前后数据对比, 精确检测写操作是否意外修改了非目标行的字段.
    """

    def test_update_changes_only_target_field(self, dal_class: Any, session: Any, make_cu: Any) -> None:
        """update 后: 目标行字段已更新, 旁观者行字段不变."""
        bystander = dal_class.create(session, make_cu("bystander"))
        target = dal_class.create(session, make_cu("target"))
        bystander_id = self._get_entity_id(bystander)
        bystander_label_before = self._get_entity_label(bystander)

        dal_class.update_only_set_by_id(session, self._get_entity_id(target), make_cu("changed"))
        self._post_write_refresh(session)

        bystander_after = dal_class.get_by_id(session, bystander_id)
        assert bystander_after is not None
        assert self._get_entity_label(bystander_after) == bystander_label_before

    def test_create_preserves_field_value(self, dal_class: Any, session: Any, make_cu: Any) -> None:
        """create 后读回实体, 字段值与 CU 输入一致."""
        entity = dal_class.create(session, make_cu("precise-value"))
        assert self._get_entity_label(entity) is not None

        found = dal_class.get_by_id(session, self._get_entity_id(entity))
        assert found is not None
        assert self._get_entity_label(found) == self._get_entity_label(entity)

    def test_delete_does_not_alter_bystander_fields(self, dal_class: Any, session: Any, make_cu: Any) -> None:
        """delete 后: 旁观者行的字段值完全不变."""
        bystander = dal_class.create(session, make_cu("keeper"))
        target = dal_class.create(session, make_cu("disposable"))
        bystander_id = self._get_entity_id(bystander)
        bystander_label = self._get_entity_label(bystander)

        dal_class.delete_by_id(session, self._get_entity_id(target))
        self._post_write_refresh(session)

        bystander_after = dal_class.get_by_id(session, bystander_id)
        assert bystander_after is not None
        assert self._get_entity_label(bystander_after) == bystander_label

    def test_multiple_creates_preserve_distinct_values(self, dal_class: Any, session: Any, make_cu: Any) -> None:
        """批量创建后, 每个实体保持自己的字段值."""
        labels = ["first", "second", "third"]
        entities = [dal_class.create(session, make_cu(lab)) for lab in labels]
        snapshots = [(self._get_entity_id(e), self._get_entity_label(e)) for e in entities]
        self._post_write_refresh(session)

        for eid, label in snapshots:
            found = dal_class.get_by_id(session, eid)
            assert found is not None
            assert self._get_entity_label(found) == label

    def test_update_actually_changes_target_value(self, dal_class: Any, session: Any, make_cu: Any) -> None:
        """update 后目标行的字段值确实发生了变更."""
        entity = dal_class.create(session, make_cu("original"))
        eid = self._get_entity_id(entity)
        original_label = self._get_entity_label(entity)

        dal_class.update_only_set_by_id(session, eid, make_cu("modified"))
        self._post_write_refresh(session)

        updated = dal_class.get_by_id(session, eid)
        assert updated is not None
        assert self._get_entity_label(updated) != original_label


class SyncLockDALConformanceTests(_ConformanceHelpers):
    """同步锁操作 DAL 一致性测试.

    需要 ``where_clause_factory`` fixture.
    """

    def test_get_by_id_for_update_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        locked = dal_class.get_by_id_for_update(session, eid)
        assert locked is not None
        assert self._get_entity_id(locked) == eid

    def test_get_by_id_for_update_nonexistent(self, dal_class: Any, session: Any) -> None:
        assert dal_class.get_by_id_for_update(session, 999999) is None

    def test_batch_get_for_update(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        e1 = dal_class.create(session, sample_cu)
        e2 = dal_class.create(session, sample_cu)
        ids = [self._get_entity_id(e1), self._get_entity_id(e2)]
        result = dal_class.batch_get_for_update(session, ids)
        assert len(result) == 2
        assert {self._get_entity_id(r) for r in result} == set(ids)

    def test_batch_get_for_update_empty(self, dal_class: Any, session: Any) -> None:
        assert dal_class.batch_get_for_update(session, []) == []

    def test_get_one_for_update(self, dal_class: Any, session: Any, sample_cu: Any, where_clause_factory: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        found = dal_class.get_one_for_update(session, where_clauses=where_clause_factory(entity))
        assert found is not None

    def test_lock_does_not_change_count(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        dal_class.create(session, sample_cu)
        entity = dal_class.create(session, sample_cu)
        count_before = dal_class.count(session)
        dal_class.get_by_id_for_update(session, self._get_entity_id(entity))
        assert dal_class.count(session) == count_before

    def test_optimistic_lock_success(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """乐观锁: 版本匹配时更新成功."""
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        version = self._get_entity_version(entity)
        updated = dal_class.update_only_set_with_optimistic_lock(
            session,
            eid,
            sample_cu,
            expected_version=version,
        )
        assert updated is not None
        assert self._get_entity_id(updated) == eid

    def test_optimistic_lock_version_mismatch(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """乐观锁: 版本不匹配时抛出可重试异常."""
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        err_cls = self._get_retryable_error_class()
        with pytest.raises(err_cls):
            dal_class.update_only_set_with_optimistic_lock(
                session,
                eid,
                sample_cu,
                expected_version=99999,
            )

    def test_optimistic_lock_increments_version(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """乐观锁: 成功后版本号递增 1."""
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        old_version = self._get_entity_version(entity)
        updated = dal_class.update_only_set_with_optimistic_lock(
            session,
            eid,
            sample_cu,
            expected_version=old_version,
        )
        assert updated is not None
        assert self._get_entity_version(updated) == old_version + 1

    def test_optimistic_lock_nonexistent(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """乐观锁: 不存在的实体返回 None 或抛出可重试异常.

        部分 ORM 实现 (如 SQLAlchemy UPDATE WHERE id=X AND version=Y) 无法区分
        「实体不存在」与「版本不匹配」, 两种行为均可接受.
        """
        err_cls = self._get_retryable_error_class()
        try:
            result = dal_class.update_only_set_with_optimistic_lock(
                session,
                999999,
                sample_cu,
                expected_version=1,
            )
            assert result is None
        except err_cls:
            pass

    def test_batch_get_for_update_partial_match(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """批量加锁: 部分 id 存在时只返回存在的实体."""
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        result = dal_class.batch_get_for_update(session, [eid, 999999])
        assert len(result) == 1
        assert self._get_entity_id(result[0]) == eid


class SyncAdvancedWriteDALConformanceTests(_ConformanceHelpers):
    """同步高级写操作 DAL 一致性测试."""

    def test_update_full_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        updated = dal_class.update_full_by_id(session, eid, sample_cu)
        assert updated is not None
        assert self._get_entity_id(updated) == eid

    def test_update_full_by_id_nonexistent(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        assert dal_class.update_full_by_id(session, 999999, sample_cu) is None

    def test_update_full_does_not_change_count(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        dal_class.create(session, sample_cu)
        entity = dal_class.create(session, sample_cu)
        count_before = dal_class.count(session)
        dal_class.update_full_by_id(session, self._get_entity_id(entity), sample_cu)
        assert dal_class.count(session) == count_before

    def test_update_full_isolation(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        bystander = dal_class.create(session, sample_cu)
        target = dal_class.create(session, sample_cu)
        bystander_id = self._get_entity_id(bystander)
        dal_class.update_full_by_id(session, self._get_entity_id(target), sample_cu)
        self._post_write_refresh(session)
        assert dal_class.get_by_id(session, bystander_id) is not None

    def test_update_partial_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        updated = dal_class.update_partial_by_id(session, eid, sample_cu)
        assert updated is not None
        assert self._get_entity_id(updated) == eid

    def test_update_partial_by_id_nonexistent(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        assert dal_class.update_partial_by_id(session, 999999, sample_cu) is None

    def test_update_partial_does_not_change_count(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        dal_class.create(session, sample_cu)
        entity = dal_class.create(session, sample_cu)
        count_before = dal_class.count(session)
        dal_class.update_partial_by_id(session, self._get_entity_id(entity), sample_cu)
        assert dal_class.count(session) == count_before

    def test_batch_update_by_ids_returns_affected(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """batch_update_by_ids 返回实际受影响行数."""
        e1 = dal_class.create(session, sample_cu)
        e2 = dal_class.create(session, sample_cu)
        affected = dal_class.batch_update_by_ids(
            session,
            entity_ids=[self._get_entity_id(e1), self._get_entity_id(e2)],
            update_data=self._make_update_data("name", "batch-updated"),
        )
        assert affected == 2

    def test_batch_update_by_ids_empty(self, dal_class: Any, session: Any) -> None:
        """空 id 集合返回 0."""
        assert (
            dal_class.batch_update_by_ids(
                session,
                entity_ids=[],
                update_data=self._make_update_data("name", "x"),
            )
            == 0
        )

    def test_batch_update_by_ids_nonexistent(self, dal_class: Any, session: Any) -> None:
        """全部不存在的 id 返回 0."""
        assert (
            dal_class.batch_update_by_ids(
                session,
                entity_ids=[999998, 999999],
                update_data=self._make_update_data("name", "x"),
            )
            == 0
        )

    def test_batch_update_by_ids_does_not_change_count(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """batch_update_by_ids 不改变总行数."""
        dal_class.create(session, sample_cu)
        dal_class.create(session, sample_cu)
        count_before = dal_class.count(session)
        dal_class.batch_update_by_ids(
            session,
            entity_ids=[self._get_entity_id(dal_class.create(session, sample_cu))],
            update_data=self._make_update_data("name", "updated"),
        )
        assert dal_class.count(session) == count_before + 1

    def test_batch_update_by_conditions_no_match(
        self,
        dal_class: Any,
        session: Any,
        make_cu: Any,
        where_clause_factory: Any,
    ) -> None:
        """无匹配行时 batch_update_by_conditions 返回 0."""
        target = dal_class.create(session, make_cu("will-delete"))
        conditions = where_clause_factory(target)
        dal_class.delete_by_id(session, self._get_entity_id(target))
        self._post_write_refresh(session)
        affected = dal_class.batch_update_by_conditions(
            session,
            conditions=conditions,
            update_data=self._make_update_data("name", "nope"),
        )
        assert affected == 0

    def test_batch_update_by_conditions_returns_affected(
        self,
        dal_class: Any,
        session: Any,
        make_cu: Any,
        where_clause_factory: Any,
    ) -> None:
        """batch_update_by_conditions 返回正确的受影响行数."""
        target = dal_class.create(session, make_cu("match-me"))
        dal_class.create(session, make_cu("not-me"))
        conditions = where_clause_factory(target)
        affected = dal_class.batch_update_by_conditions(
            session,
            conditions=conditions,
            update_data=self._make_update_data("name", "changed"),
        )
        assert affected == 1


class SyncAdvancedWriteFieldIsolationDALConformanceTests(_ConformanceHelpers):
    """同步高级写字段级隔离性测试. 需要 ``make_cu``."""

    def test_update_full_changes_only_target(self, dal_class: Any, session: Any, make_cu: Any) -> None:
        bystander = dal_class.create(session, make_cu("keep"))
        target = dal_class.create(session, make_cu("replace"))
        bystander_id = self._get_entity_id(bystander)
        bystander_label = self._get_entity_label(bystander)

        dal_class.update_full_by_id(session, self._get_entity_id(target), make_cu("replaced"))
        self._post_write_refresh(session)

        assert self._get_entity_label(dal_class.get_by_id(session, bystander_id)) == bystander_label

    def test_update_partial_changes_only_target(self, dal_class: Any, session: Any, make_cu: Any) -> None:
        bystander = dal_class.create(session, make_cu("stable"))
        target = dal_class.create(session, make_cu("mutable"))
        bystander_id = self._get_entity_id(bystander)
        bystander_label = self._get_entity_label(bystander)

        dal_class.update_partial_by_id(session, self._get_entity_id(target), make_cu("mutated"))
        self._post_write_refresh(session)

        assert self._get_entity_label(dal_class.get_by_id(session, bystander_id)) == bystander_label


# ===== Sync Composed =====


class SyncBaseDALConformanceTests(SyncReadDALConformanceTests, SyncWriteDALConformanceTests):
    """同步 CRUD DAL 一致性测试 (Read + Write)."""


class SyncFullDALConformanceTests(
    SyncReadDALConformanceTests,
    SyncWriteDALConformanceTests,
    SyncFieldIsolationDALConformanceTests,
    SyncLockDALConformanceTests,
    SyncAdvancedWriteDALConformanceTests,
    SyncAdvancedWriteFieldIsolationDALConformanceTests,
):
    """同步完整 DAL 一致性测试 (Read + Write + Lock + AdvancedWrite + FieldIsolation)."""


# ===== Async =====


class AsyncReadDALConformanceTests(_ConformanceHelpers):
    """异步 Read DAL 一致性测试."""

    async def test_get_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        found = await dal_class.get_by_id(session, eid)
        assert found is not None
        assert self._get_entity_id(found) == eid

    async def test_get_by_id_nonexistent(self, dal_class: Any, session: Any) -> None:
        assert await dal_class.get_by_id(session, 999999) is None

    async def test_ret_dto_after_get_by_id(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        dto = await dal_class.ret_dto_after_get_by_id(session, self._get_entity_id(entity))
        assert dto is not None
        assert hasattr(dto, "id")

    async def test_ret_dto_after_get_by_id_nonexistent(self, dal_class: Any, session: Any) -> None:
        assert await dal_class.ret_dto_after_get_by_id(session, 999999) is None

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

    async def test_get_all_returns_exact_count(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        initial_count = await dal_class.count(session)
        await dal_class.create(session, sample_cu)
        await dal_class.create(session, sample_cu)
        all_records = await dal_class.get_all(session, skip=0, limit=9999)
        assert len(all_records) == initial_count + 2

    async def test_count_returns_int(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        initial = await dal_class.count(session)
        assert isinstance(initial, int)
        await dal_class.create(session, sample_cu)
        assert await dal_class.count(session) == initial + 1

    async def test_exists_true_for_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        assert await dal_class.exists(session, self._get_entity_id(entity)) is True

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

    async def test_get_all_skip_beyond_total(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        await dal_class.create(session, sample_cu)
        total = await dal_class.count(session)
        result = await dal_class.get_all(session, skip=total + 100, limit=10)
        assert result == []

    async def test_batch_get_with_empty_list(self, dal_class: Any, session: Any) -> None:
        assert await dal_class.batch_get_id__entity(session, []) == {}
        assert await dal_class.batch_get_id__dto(session, []) == {}

    async def test_get_by_id_read_your_writes(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        found = await dal_class.get_by_id(session, eid)
        assert found is not None
        assert self._get_entity_id(found) == eid

    async def test_count_zero_on_empty(self, dal_class: Any, session: Any) -> None:
        initial = await dal_class.count(session)
        assert isinstance(initial, int)
        assert initial >= 0

    async def test_exists_consistency_with_get_by_id(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        assert await dal_class.exists(session, eid) == (await dal_class.get_by_id(session, eid) is not None)
        assert not await dal_class.exists(session, 999999)
        assert await dal_class.get_by_id(session, 999999) is None

    async def test_get_all_pagination_no_overlap(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """分页结果之间不应有 id 重叠."""
        for _ in range(3):
            await dal_class.create(session, sample_cu)
        page1 = await dal_class.get_all(session, skip=0, limit=2)
        page2 = await dal_class.get_all(session, skip=2, limit=2)
        ids1 = {dto.id for dto in page1}
        ids2 = {dto.id for dto in page2}
        assert ids1.isdisjoint(ids2)

    async def test_iter_count_matches_count(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """iter_record_dtos 总数应与 count() 一致."""
        await dal_class.create(session, sample_cu)
        await dal_class.create(session, sample_cu)
        count = await dal_class.count(session)
        iter_count = len([dto async for dto in dal_class.iter_record_dtos(session)])
        assert iter_count == count

    async def test_batch_get_deduplicates(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """batch_get 传入重复 id 时, 结果集 key 不重复."""
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        result = await dal_class.batch_get_id__entity(session, [eid, eid, eid])
        assert len(result) == 1
        assert eid in result


class AsyncWriteDALConformanceTests(_ConformanceHelpers):
    """异步 Write DAL 一致性测试."""

    async def test_create_returns_entity(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        assert entity is not None
        assert hasattr(entity, "id")

    async def test_create_increments_count(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        before = await dal_class.count(session)
        await dal_class.create(session, sample_cu)
        assert await dal_class.count(session) == before + 1

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
        assert self._get_entity_id(updated) == eid

    async def test_update_only_set_by_id_nonexistent(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        assert await dal_class.update_only_set_by_id(session, 999999, sample_cu) is None

    async def test_update_does_not_change_count(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        await dal_class.create(session, sample_cu)
        entity = await dal_class.create(session, sample_cu)
        count_before = await dal_class.count(session)
        await dal_class.update_only_set_by_id(session, self._get_entity_id(entity), sample_cu)
        assert await dal_class.count(session) == count_before

    async def test_update_isolation(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        bystander = await dal_class.create(session, sample_cu)
        target = await dal_class.create(session, sample_cu)
        bystander_id = self._get_entity_id(bystander)
        await dal_class.update_only_set_by_id(session, self._get_entity_id(target), sample_cu)
        self._post_write_refresh(session)
        assert await dal_class.get_by_id(session, bystander_id) is not None

    async def test_ret_dto_after_update_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        dto = await dal_class.ret_dto_after_update_by_id(session, self._get_entity_id(entity), sample_cu)
        assert dto is not None

    async def test_ret_dto_after_update_by_id_nonexistent(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        assert await dal_class.ret_dto_after_update_by_id(session, 999999, sample_cu) is None

    async def test_delete_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        assert await dal_class.delete_by_id(session, self._get_entity_id(entity)) is True

    async def test_delete_by_id_nonexistent(self, dal_class: Any, session: Any) -> None:
        assert await dal_class.delete_by_id(session, 999999) is False

    async def test_delete_decrements_count(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        count_before = await dal_class.count(session)
        await dal_class.delete_by_id(session, self._get_entity_id(entity))
        assert await dal_class.count(session) == count_before - 1

    async def test_delete_isolation(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        bystander = await dal_class.create(session, sample_cu)
        target = await dal_class.create(session, sample_cu)
        bystander_id = self._get_entity_id(bystander)
        await dal_class.delete_by_id(session, self._get_entity_id(target))
        self._post_write_refresh(session)
        assert await dal_class.get_by_id(session, bystander_id) is not None

    async def test_delete_then_get_returns_none(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        await dal_class.delete_by_id(session, eid)
        self._post_write_refresh(session)
        assert await dal_class.get_by_id(session, eid) is None

    async def test_delete_idempotent(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        assert await dal_class.delete_by_id(session, eid) is True
        assert await dal_class.delete_by_id(session, eid) is False

    async def test_mixed_ops_count_accuracy(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        initial = await dal_class.count(session)
        e1 = await dal_class.create(session, sample_cu)
        await dal_class.create(session, sample_cu)
        await dal_class.create(session, sample_cu)
        await dal_class.delete_by_id(session, self._get_entity_id(e1))
        assert await dal_class.count(session) == initial + 2

    async def test_update_preserves_id(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        updated = await dal_class.update_only_set_by_id(session, eid, sample_cu)
        assert updated is not None
        assert self._get_entity_id(updated) == eid

    async def test_exists_false_after_delete(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        assert await dal_class.exists(session, eid) is True
        await dal_class.delete_by_id(session, eid)
        self._post_write_refresh(session)
        assert await dal_class.exists(session, eid) is False

    async def test_dto_fields_match_entity(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        dto = await dal_class.ret_dto_after_get_by_id(session, eid)
        assert dto is not None
        assert dto.id == eid

    async def test_create_unique_ids(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """多次 create 返回互不相同的 id."""
        ids = set()
        for _ in range(5):
            entity = await dal_class.create(session, sample_cu)
            ids.add(self._get_entity_id(entity))
        assert len(ids) == 5

    async def test_ret_dto_after_create_id_findable(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """ret_dto_after_create 返回的 id 可通过 get_by_id 找回."""
        dto = await dal_class.ret_dto_after_create(session, sample_cu)
        assert await dal_class.get_by_id(session, dto.id) is not None


class AsyncFieldIsolationDALConformanceTests(_ConformanceHelpers):
    """异步字段级隔离性验证.

    需要 ``make_cu`` fixture. 通过前后数据对比, 精确检测写操作是否意外修改了非目标行的字段.
    """

    async def test_update_changes_only_target_field(self, dal_class: Any, session: Any, make_cu: Any) -> None:
        bystander = await dal_class.create(session, make_cu("bystander"))
        target = await dal_class.create(session, make_cu("target"))
        bystander_id = self._get_entity_id(bystander)
        bystander_label_before = self._get_entity_label(bystander)

        await dal_class.update_only_set_by_id(session, self._get_entity_id(target), make_cu("changed"))
        self._post_write_refresh(session)

        bystander_after = await dal_class.get_by_id(session, bystander_id)
        assert bystander_after is not None
        assert self._get_entity_label(bystander_after) == bystander_label_before

    async def test_create_preserves_field_value(self, dal_class: Any, session: Any, make_cu: Any) -> None:
        entity = await dal_class.create(session, make_cu("precise-value"))
        original_label = self._get_entity_label(entity)
        assert original_label is not None

        found = await dal_class.get_by_id(session, self._get_entity_id(entity))
        assert found is not None
        assert self._get_entity_label(found) == original_label

    async def test_delete_does_not_alter_bystander_fields(self, dal_class: Any, session: Any, make_cu: Any) -> None:
        bystander = await dal_class.create(session, make_cu("keeper"))
        target = await dal_class.create(session, make_cu("disposable"))
        bystander_id = self._get_entity_id(bystander)
        bystander_label = self._get_entity_label(bystander)

        await dal_class.delete_by_id(session, self._get_entity_id(target))
        self._post_write_refresh(session)

        bystander_after = await dal_class.get_by_id(session, bystander_id)
        assert bystander_after is not None
        assert self._get_entity_label(bystander_after) == bystander_label

    async def test_multiple_creates_preserve_distinct_values(self, dal_class: Any, session: Any, make_cu: Any) -> None:
        labels = ["first", "second", "third"]
        entities = [await dal_class.create(session, make_cu(lab)) for lab in labels]
        snapshots = [(self._get_entity_id(e), self._get_entity_label(e)) for e in entities]
        self._post_write_refresh(session)

        for eid, label in snapshots:
            found = await dal_class.get_by_id(session, eid)
            assert found is not None
            assert self._get_entity_label(found) == label

    async def test_update_actually_changes_target_value(self, dal_class: Any, session: Any, make_cu: Any) -> None:
        """update 后目标行的字段值确实发生了变更."""
        entity = await dal_class.create(session, make_cu("original"))
        eid = self._get_entity_id(entity)
        original_label = self._get_entity_label(entity)

        await dal_class.update_only_set_by_id(session, eid, make_cu("modified"))
        self._post_write_refresh(session)

        updated = await dal_class.get_by_id(session, eid)
        assert updated is not None
        assert self._get_entity_label(updated) != original_label


class AsyncLockDALConformanceTests(_ConformanceHelpers):
    """异步锁操作 DAL 一致性测试.

    需要 ``where_clause_factory`` fixture.
    """

    async def test_get_by_id_for_update_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        locked = await dal_class.get_by_id_for_update(session, eid)
        assert locked is not None
        assert self._get_entity_id(locked) == eid

    async def test_get_by_id_for_update_nonexistent(self, dal_class: Any, session: Any) -> None:
        assert await dal_class.get_by_id_for_update(session, 999999) is None

    async def test_batch_get_for_update(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        e1 = await dal_class.create(session, sample_cu)
        e2 = await dal_class.create(session, sample_cu)
        ids = [self._get_entity_id(e1), self._get_entity_id(e2)]
        result = await dal_class.batch_get_for_update(session, ids)
        assert len(result) == 2
        assert {self._get_entity_id(r) for r in result} == set(ids)

    async def test_batch_get_for_update_empty(self, dal_class: Any, session: Any) -> None:
        assert await dal_class.batch_get_for_update(session, []) == []

    async def test_get_one_for_update(self, dal_class: Any, session: Any, sample_cu: Any, where_clause_factory: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        found = await dal_class.get_one_for_update(session, where_clauses=where_clause_factory(entity))
        assert found is not None

    async def test_lock_does_not_change_count(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        await dal_class.create(session, sample_cu)
        entity = await dal_class.create(session, sample_cu)
        count_before = await dal_class.count(session)
        await dal_class.get_by_id_for_update(session, self._get_entity_id(entity))
        assert await dal_class.count(session) == count_before

    async def test_optimistic_lock_success(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """乐观锁: 版本匹配时更新成功."""
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        version = self._get_entity_version(entity)
        updated = await dal_class.update_only_set_with_optimistic_lock(
            session,
            eid,
            sample_cu,
            expected_version=version,
        )
        assert updated is not None
        assert self._get_entity_id(updated) == eid

    async def test_optimistic_lock_version_mismatch(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """乐观锁: 版本不匹配时抛出可重试异常."""
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        err_cls = self._get_retryable_error_class()
        with pytest.raises(err_cls):
            await dal_class.update_only_set_with_optimistic_lock(
                session,
                eid,
                sample_cu,
                expected_version=99999,
            )

    async def test_optimistic_lock_increments_version(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """乐观锁: 成功后版本号递增 1."""
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        old_version = self._get_entity_version(entity)
        updated = await dal_class.update_only_set_with_optimistic_lock(
            session,
            eid,
            sample_cu,
            expected_version=old_version,
        )
        assert updated is not None
        assert self._get_entity_version(updated) == old_version + 1

    async def test_optimistic_lock_nonexistent(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """乐观锁: 不存在的实体返回 None 或抛出可重试异常.

        部分 ORM 实现 (如 SQLAlchemy UPDATE WHERE id=X AND version=Y) 无法区分
        「实体不存在」与「版本不匹配」, 两种行为均可接受.
        """
        err_cls = self._get_retryable_error_class()
        try:
            result = await dal_class.update_only_set_with_optimistic_lock(
                session,
                999999,
                sample_cu,
                expected_version=1,
            )
            assert result is None
        except err_cls:
            pass

    async def test_batch_get_for_update_partial_match(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """批量加锁: 部分 id 存在时只返回存在的实体."""
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        result = await dal_class.batch_get_for_update(session, [eid, 999999])
        assert len(result) == 1
        assert self._get_entity_id(result[0]) == eid


class AsyncAdvancedWriteDALConformanceTests(_ConformanceHelpers):
    """异步高级写操作 DAL 一致性测试."""

    async def test_update_full_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        updated = await dal_class.update_full_by_id(session, eid, sample_cu)
        assert updated is not None
        assert self._get_entity_id(updated) == eid

    async def test_update_full_by_id_nonexistent(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        assert await dal_class.update_full_by_id(session, 999999, sample_cu) is None

    async def test_update_full_does_not_change_count(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        await dal_class.create(session, sample_cu)
        entity = await dal_class.create(session, sample_cu)
        count_before = await dal_class.count(session)
        await dal_class.update_full_by_id(session, self._get_entity_id(entity), sample_cu)
        assert await dal_class.count(session) == count_before

    async def test_update_full_isolation(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        bystander = await dal_class.create(session, sample_cu)
        target = await dal_class.create(session, sample_cu)
        bystander_id = self._get_entity_id(bystander)
        await dal_class.update_full_by_id(session, self._get_entity_id(target), sample_cu)
        self._post_write_refresh(session)
        assert await dal_class.get_by_id(session, bystander_id) is not None

    async def test_update_partial_by_id_existing(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        entity = await dal_class.create(session, sample_cu)
        eid = self._get_entity_id(entity)
        updated = await dal_class.update_partial_by_id(session, eid, sample_cu)
        assert updated is not None
        assert self._get_entity_id(updated) == eid

    async def test_update_partial_by_id_nonexistent(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        assert await dal_class.update_partial_by_id(session, 999999, sample_cu) is None

    async def test_update_partial_does_not_change_count(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        await dal_class.create(session, sample_cu)
        entity = await dal_class.create(session, sample_cu)
        count_before = await dal_class.count(session)
        await dal_class.update_partial_by_id(session, self._get_entity_id(entity), sample_cu)
        assert await dal_class.count(session) == count_before

    async def test_batch_update_by_ids_returns_affected(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """batch_update_by_ids 返回实际受影响行数."""
        e1 = await dal_class.create(session, sample_cu)
        e2 = await dal_class.create(session, sample_cu)
        affected = await dal_class.batch_update_by_ids(
            session,
            entity_ids=[self._get_entity_id(e1), self._get_entity_id(e2)],
            update_data=self._make_update_data("name", "batch-updated"),
        )
        assert affected == 2

    async def test_batch_update_by_ids_empty(self, dal_class: Any, session: Any) -> None:
        """空 id 集合返回 0."""
        assert (
            await dal_class.batch_update_by_ids(
                session,
                entity_ids=[],
                update_data=self._make_update_data("name", "x"),
            )
            == 0
        )

    async def test_batch_update_by_ids_nonexistent(self, dal_class: Any, session: Any) -> None:
        """全部不存在的 id 返回 0."""
        assert (
            await dal_class.batch_update_by_ids(
                session,
                entity_ids=[999998, 999999],
                update_data=self._make_update_data("name", "x"),
            )
            == 0
        )

    async def test_batch_update_by_ids_does_not_change_count(self, dal_class: Any, session: Any, sample_cu: Any) -> None:
        """batch_update_by_ids 不改变总行数."""
        await dal_class.create(session, sample_cu)
        await dal_class.create(session, sample_cu)
        count_before = await dal_class.count(session)
        e3 = await dal_class.create(session, sample_cu)
        await dal_class.batch_update_by_ids(
            session,
            entity_ids=[self._get_entity_id(e3)],
            update_data=self._make_update_data("name", "updated"),
        )
        assert await dal_class.count(session) == count_before + 1

    async def test_batch_update_by_conditions_no_match(
        self,
        dal_class: Any,
        session: Any,
        make_cu: Any,
        where_clause_factory: Any,
    ) -> None:
        """无匹配行时 batch_update_by_conditions 返回 0."""
        target = await dal_class.create(session, make_cu("will-delete"))
        conditions = where_clause_factory(target)
        await dal_class.delete_by_id(session, self._get_entity_id(target))
        self._post_write_refresh(session)
        affected = await dal_class.batch_update_by_conditions(
            session,
            conditions=conditions,
            update_data=self._make_update_data("name", "nope"),
        )
        assert affected == 0

    async def test_batch_update_by_conditions_returns_affected(
        self,
        dal_class: Any,
        session: Any,
        make_cu: Any,
        where_clause_factory: Any,
    ) -> None:
        """batch_update_by_conditions 返回正确的受影响行数."""
        target = await dal_class.create(session, make_cu("match-me"))
        await dal_class.create(session, make_cu("not-me"))
        conditions = where_clause_factory(target)
        affected = await dal_class.batch_update_by_conditions(
            session,
            conditions=conditions,
            update_data=self._make_update_data("name", "changed"),
        )
        assert affected == 1


class AsyncAdvancedWriteFieldIsolationDALConformanceTests(_ConformanceHelpers):
    """异步高级写字段级隔离性测试. 需要 ``make_cu``."""

    async def test_update_full_changes_only_target(self, dal_class: Any, session: Any, make_cu: Any) -> None:
        bystander = await dal_class.create(session, make_cu("keep"))
        target = await dal_class.create(session, make_cu("replace"))
        bystander_id = self._get_entity_id(bystander)
        bystander_label = self._get_entity_label(bystander)

        await dal_class.update_full_by_id(session, self._get_entity_id(target), make_cu("replaced"))
        self._post_write_refresh(session)

        assert self._get_entity_label(await dal_class.get_by_id(session, bystander_id)) == bystander_label

    async def test_update_partial_changes_only_target(self, dal_class: Any, session: Any, make_cu: Any) -> None:
        bystander = await dal_class.create(session, make_cu("stable"))
        target = await dal_class.create(session, make_cu("mutable"))
        bystander_id = self._get_entity_id(bystander)
        bystander_label = self._get_entity_label(bystander)

        await dal_class.update_partial_by_id(session, self._get_entity_id(target), make_cu("mutated"))
        self._post_write_refresh(session)

        assert self._get_entity_label(await dal_class.get_by_id(session, bystander_id)) == bystander_label


# ===== Async Composed =====


class AsyncBaseDALConformanceTests(AsyncReadDALConformanceTests, AsyncWriteDALConformanceTests):
    """异步 CRUD DAL 一致性测试 (Read + Write)."""


class AsyncFullDALConformanceTests(
    AsyncReadDALConformanceTests,
    AsyncWriteDALConformanceTests,
    AsyncFieldIsolationDALConformanceTests,
    AsyncLockDALConformanceTests,
    AsyncAdvancedWriteDALConformanceTests,
    AsyncAdvancedWriteFieldIsolationDALConformanceTests,
):
    """异步完整 DAL 一致性测试 (Read + Write + Lock + AdvancedWrite + FieldIsolation)."""
