"""DynamicDAL BDD 步骤定义 + 场景注册.

遵循现有 BDD 架构:
- Given: 通过 DAL 创建测试数据
- When:  通过 DAL 执行业务操作
- Then:  通过裸 SQLAlchemy 直接验证数据库物理状态
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Generator
from typing import Any

import pytest
import sqlalchemy as sa
from pydantic import BaseModel
from pytest_bdd import given, parsers, scenario, then, when
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from lush_sqlalchemyx.base.dal._dynamic import (
    DynamicSyncDAL,
    TableRef,
)

# ════════════════════════════════════════════════════════════════
# 模型定义 (无 ORM Table class, 只有 Pydantic)
# ════════════════════════════════════════════════════════════════


class _DynCU(BaseModel):
    name: str


class _DynDTO(BaseModel):
    id: int = 0
    name: str


class _DynSoftDTO(BaseModel):
    id: int
    name: str
    is_delete: int = 0


class _DynReadonlyDTO(BaseModel):
    id: int
    user_id: int
    total: int


# ════════════════════════════════════════════════════════════════
# DAL 实例
# ════════════════════════════════════════════════════════════════

_dyn_ref = TableRef.of("dyn_items", _DynDTO)
_dyn_dal = DynamicSyncDAL(_dyn_ref, _DynDTO)

_dyn_soft_ref = TableRef.with_soft_delete("dyn_items_soft", _DynSoftDTO, soft_delete_column="is_delete")
_dyn_soft_dal = DynamicSyncDAL(_dyn_soft_ref, _DynSoftDTO)

_dyn_ro_ref = TableRef.readonly("dyn_readonly", _DynReadonlyDTO)
_dyn_ro_dal = DynamicSyncDAL(_dyn_ro_ref, _DynReadonlyDTO)


# ════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════


@pytest.fixture
def dyn_context() -> dict[str, Any]:
    return {}


def _create_engine_and_tables(*, soft_delete: bool = False) -> tuple[Any, Any]:
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="bdd_dyn_")
    os.close(fd)
    engine = create_engine(f"sqlite:///{db_path}", poolclass=NullPool)

    with engine.begin() as conn:
        conn.execute(
            sa.text("""
            CREATE TABLE dyn_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            )
        """)
        )
        conn.execute(
            sa.text("""
            CREATE TABLE dyn_items_soft (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                is_delete INTEGER DEFAULT 0
            )
        """)
        )
        conn.execute(
            sa.text("""
            CREATE TABLE dyn_readonly (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                total INTEGER NOT NULL
            )
        """)
        )
        conn.execute(sa.text("INSERT INTO dyn_readonly (id, user_id, total) VALUES (1, 100, 42)"))

    return engine, db_path


@pytest.fixture
def dyn_session() -> Generator[Session, None, None]:
    engine, db_path = _create_engine_and_tables()
    try:
        SessionLocal = sessionmaker(bind=engine)
        with SessionLocal() as session:
            yield session
    finally:
        engine.dispose()
        if os.path.exists(db_path):
            os.unlink(db_path)


# ════════════════════════════════════════════════════════════════
# 裸 SQL 验证辅助
# ════════════════════════════════════════════════════════════════


def _raw_count(session: Session, table: str, where: str | None = None, params: dict[str, Any] | None = None) -> int:
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    return session.execute(sa.text(sql), params or {}).scalar()


def _raw_exists(session: Session, table: str, entity_id: int) -> bool:
    return session.execute(sa.text(f"SELECT 1 FROM {table} WHERE id = :id"), {"id": entity_id}).scalar() is not None


def _raw_col(session: Session, table: str, entity_id: int, col: str) -> Any:
    return session.execute(sa.text(f"SELECT {col} FROM {table} WHERE id = :id"), {"id": entity_id}).scalar()


# ════════════════════════════════════════════════════════════════
# Given 步骤
# ════════════════════════════════════════════════════════════════


@given("DynamicDAL 数据库连接已就绪")
def given_dyn_db_ready(dyn_session: Session) -> None:
    pass


@given("DynamicDAL 带软删除的数据库连接已就绪")
def given_dyn_soft_db_ready(dyn_session: Session) -> None:
    pass


@given("DynamicDAL 只读表的数据库连接已就绪")
def given_dyn_ro_db_ready(dyn_context: dict[str, Any], dyn_session: Session) -> None:
    dyn_context["active_dal"] = _dyn_ro_dal


@given(parsers.parse('DynamicDAL 已存在一条名称为 "{name}" 的记录'))
def given_dyn_existing_record(name: str, dyn_context: dict[str, Any], dyn_session: Session) -> None:
    dto = _dyn_dal.create(_DynCU(name=name), session=dyn_session)
    dyn_context["entity_id"] = dto.id
    dyn_context["last_name"] = name
    dyn_session.commit()


@given(parsers.parse('DynamicDAL 软删除表已存在一条名称为 "{name}" 的记录'))
def given_dyn_soft_existing_record(name: str, dyn_context: dict[str, Any], dyn_session: Session) -> None:
    dyn_context["active_dal"] = _dyn_soft_dal
    dto = _dyn_soft_dal.create(_DynCU(name=name), session=dyn_session)
    dyn_context["entity_id"] = dto.id
    dyn_context["last_name"] = name
    dyn_session.commit()


# ════════════════════════════════════════════════════════════════
# When 步骤
# ════════════════════════════════════════════════════════════════


@when(parsers.parse('DynamicDAL 创建一条名称为 "{name}" 的记录'))
def when_dyn_create(name: str, dyn_context: dict[str, Any], dyn_session: Session) -> None:
    dto = _dyn_dal.create(_DynCU(name=name), session=dyn_session)
    dyn_context["op_result"] = dto
    dyn_context["entity_id"] = dto.id
    dyn_session.commit()


@when("DynamicDAL 通过 ID 查询该记录")
def when_dyn_get_by_id(dyn_context: dict[str, Any], dyn_session: Session) -> None:
    dyn_context["op_result"] = _dyn_dal.get_by_id(dyn_context["entity_id"], session=dyn_session)


@when(parsers.parse('DynamicDAL 查询不存在的记录 ID "{eid:d}"'))
def when_dyn_get_nonexistent(eid: int, dyn_context: dict[str, Any], dyn_session: Session) -> None:
    dyn_context["op_result"] = _dyn_dal.get_by_id(eid, session=dyn_session)


@when(parsers.parse('DynamicDAL 使用新 CU 将记录名称更新为 "{name}"'))
def when_dyn_update(name: str, dyn_context: dict[str, Any], dyn_session: Session) -> None:
    dyn_context["op_result"] = _dyn_dal.update_by_id(dyn_context["entity_id"], _DynCU(name=name), session=dyn_session)
    dyn_session.commit()


@when("DynamicDAL 删除该记录")
def when_dyn_delete(dyn_context: dict[str, Any], dyn_session: Session) -> None:
    dal = dyn_context.get("active_dal", _dyn_dal)
    dyn_context["op_result"] = dal.delete_by_id(dyn_context["entity_id"], session=dyn_session)
    dyn_session.commit()


@when(parsers.parse('DynamicDAL 删除不存在的记录 ID "{eid:d}"'))
def when_dyn_delete_nonexistent(eid: int, dyn_context: dict[str, Any], dyn_session: Session) -> None:
    dyn_context["op_result"] = _dyn_soft_dal.delete_by_id(eid, session=dyn_session)


@when("DynamicDAL 恢复该记录")
def when_dyn_restore(dyn_context: dict[str, Any], dyn_session: Session) -> None:
    dyn_context["op_result"] = _dyn_soft_dal.restore_by_id(dyn_context["entity_id"], session=dyn_session)
    dyn_session.commit()


@when(parsers.parse("DynamicDAL 批量创建 {count:d} 条记录"))
def when_dyn_bulk_create(count: int, dyn_context: dict[str, Any], dyn_session: Session) -> None:
    cus = [_DynCU(name=f"bulk_{i}") for i in range(count)]
    dyn_context["op_result"] = _dyn_dal.bulk_create(cus, session=dyn_session)
    dyn_session.commit()


@when(parsers.parse('DynamicDAL 按条件查询名称为 "{name}"'))
def when_dyn_list_by(name: str, dyn_context: dict[str, Any], dyn_session: Session) -> None:
    dyn_context["op_result"] = _dyn_dal.list_by([sa.column("name") == name], session=dyn_session)


@when("DynamicDAL 统计记录总数")
def when_dyn_count(dyn_context: dict[str, Any], dyn_session: Session) -> None:
    dyn_context["op_result"] = _dyn_dal.count_by(session=dyn_session)


@when(parsers.parse("DynamicDAL 查询只读表 ID 为 {eid:d} 的记录"))
def when_dyn_ro_get(eid: int, dyn_context: dict[str, Any], dyn_session: Session) -> None:
    dyn_context["op_result"] = _dyn_ro_dal.get_by_id(eid, session=dyn_session)


@when("DynamicDAL 尝试在只读表创建记录")
def when_dyn_ro_create(dyn_context: dict[str, Any], dyn_session: Session) -> None:
    try:
        _dyn_ro_dal.create(_DynCU(name="blocked"), session=dyn_session)
        dyn_context["blocked"] = False
    except TypeError:
        dyn_context["blocked"] = True


@when("DynamicDAL 尝试在只读表更新记录")
def when_dyn_ro_update(dyn_context: dict[str, Any], dyn_session: Session) -> None:
    try:
        _dyn_ro_dal.update_by_id(1, _DynCU(name="blocked"), session=dyn_session)
        dyn_context["blocked"] = False
    except TypeError:
        dyn_context["blocked"] = True


@when("DynamicDAL 尝试在只读表删除记录")
def when_dyn_ro_delete(dyn_context: dict[str, Any], dyn_session: Session) -> None:
    try:
        _dyn_ro_dal.delete_by_id(1, session=dyn_session)
        dyn_context["blocked"] = False
    except TypeError:
        dyn_context["blocked"] = True


@when("DynamicDAL 尝试在只读表批量创建")
def when_dyn_ro_bulk_create(dyn_context: dict[str, Any], dyn_session: Session) -> None:
    try:
        _dyn_ro_dal.bulk_create([_DynCU(name="blocked")], session=dyn_session)
        dyn_context["blocked"] = False
    except TypeError:
        dyn_context["blocked"] = True


# ════════════════════════════════════════════════════════════════
# Then 步骤 — 裸 SQLAlchemy 验证
# ════════════════════════════════════════════════════════════════


@then("DynamicDAL 返回的 DTO 不为空")
def then_dyn_result_not_none(dyn_context: dict[str, Any]) -> None:
    assert dyn_context["op_result"] is not None


@then("DynamicDAL 返回的结果为空")
def then_dyn_result_none(dyn_context: dict[str, Any]) -> None:
    assert dyn_context["op_result"] is None


@then(parsers.parse('DynamicDAL 返回的 DTO 名称应为 "{expected}"'))
def then_dyn_dto_name(dyn_context: dict[str, Any], expected: str) -> None:
    r = dyn_context["op_result"]
    assert r is not None
    assert r.name == expected


@then(parsers.parse("DynamicDAL 返回的受影响行数为 {n:d}"))
def then_dyn_affected(dyn_context: dict[str, Any], n: int) -> None:
    assert dyn_context["op_result"] == n


@then("DynamicDAL 返回的结果为 True")
def then_dyn_result_true(dyn_context: dict[str, Any]) -> None:
    assert dyn_context["op_result"] is True


@then("DynamicDAL 返回的结果为 False")
def then_dyn_result_false(dyn_context: dict[str, Any]) -> None:
    assert dyn_context["op_result"] is False


@then(parsers.parse("DynamicDAL 批量创建返回 {n:d}"))
def then_dyn_bulk_count(dyn_context: dict[str, Any], n: int) -> None:
    assert dyn_context["op_result"] == n


@then(parsers.parse("DynamicDAL 列表查询至少有 {n:d} 条"))
def then_dyn_list_at_least(dyn_context: dict[str, Any], dyn_session: Session, n: int) -> None:
    dtos = _dyn_dal.list_by(session=dyn_session)
    assert len(dtos) >= n


@then(parsers.parse("DynamicDAL 条件查询结果至少有 {n:d} 条"))
def then_dyn_list_by_at_least(dyn_context: dict[str, Any], n: int) -> None:
    r = dyn_context["op_result"]
    assert isinstance(r, (list, tuple))
    assert len(r) >= n


@then(parsers.parse("DynamicDAL 返回的记录总数至少为 {n:d}"))
def then_dyn_count_at_least(dyn_context: dict[str, Any], n: int) -> None:
    assert isinstance(dyn_context["op_result"], int)
    assert dyn_context["op_result"] >= n


# ── 软删除裸 SQL 验证 ──


@then("DynamicDAL 删除后查询结果为空")
def then_dyn_soft_deleted_not_found(dyn_context: dict[str, Any], dyn_session: Session) -> None:
    # 裸 SQL 验证: is_delete=1
    val = _raw_col(dyn_session, "dyn_items_soft", dyn_context["entity_id"], "is_delete")
    assert val == 1, f"期望 is_delete=1, 实际={val}"
    # DAL 层验证: 查不到
    dto = _dyn_soft_dal.get_by_id(dyn_context["entity_id"], session=dyn_session)
    assert dto is None


@then("DynamicDAL 列表查询不包含已删除记录")
def then_dyn_soft_list_excludes(dyn_context: dict[str, Any], dyn_session: Session) -> None:
    dtos = _dyn_soft_dal.list_by(session=dyn_session)
    ids = {d.id for d in dtos}
    assert dyn_context["entity_id"] not in ids, "列表不应包含已删除记录"


@then("DynamicDAL 软删除后计数正确")
def then_dyn_soft_count_correct(dyn_context: dict[str, Any], dyn_session: Session) -> None:
    # 裸 SQL: 总数
    total = _raw_count(dyn_session, "dyn_items_soft")
    # DAL: 排除已删除
    active = _dyn_soft_dal.count_by(session=dyn_session)
    assert active == total - 1, f"期望 active={total - 1}, 实际={active}"


@then("DynamicDAL 恢复后查询结果不为空")
def then_dyn_restore_found(dyn_context: dict[str, Any], dyn_session: Session) -> None:
    # 裸 SQL: is_delete=0
    val = _raw_col(dyn_session, "dyn_items_soft", dyn_context["entity_id"], "is_delete")
    assert val == 0, f"期望 is_delete=0, 实际={val}"
    # DAL 层: 可查到
    dto = _dyn_soft_dal.get_by_id(dyn_context["entity_id"], session=dyn_session)
    assert dto is not None


@then("DynamicDAL 操作被阻止")
def then_dyn_blocked(dyn_context: dict[str, Any]) -> None:
    assert dyn_context.get("blocked") is True


# ════════════════════════════════════════════════════════════════
# 场景注册
# ════════════════════════════════════════════════════════════════

# ── dynamic-crud.feature ──


@scenario("dal/dynamic-crud.feature", "创建记录并返回 DTO")
def test_dyn_create() -> None: ...


@scenario("dal/dynamic-crud.feature", "通过 ID 查询已存在的记录")
def test_dyn_get_existing() -> None: ...


@scenario("dal/dynamic-crud.feature", "通过 ID 查询不存在的记录")
def test_dyn_get_nonexistent() -> None: ...


@scenario("dal/dynamic-crud.feature", "更新已存在的记录")
def test_dyn_update() -> None: ...


@scenario("dal/dynamic-crud.feature", "删除已存在的记录 (硬删除)")
def test_dyn_hard_delete() -> None: ...


@scenario("dal/dynamic-crud.feature", "批量创建记录")
def test_dyn_bulk_create() -> None: ...


@scenario("dal/dynamic-crud.feature", "条件查询")
def test_dyn_list_by() -> None: ...


@scenario("dal/dynamic-crud.feature", "条件计数")
def test_dyn_count_by() -> None: ...


# ── dynamic-soft-delete.feature ──


@scenario("dal/dynamic-soft-delete.feature", "软删除后查询返回空")
def test_dyn_soft_delete_visibility() -> None: ...


@scenario("dal/dynamic-soft-delete.feature", "软删除后列表排除已删除")
def test_dyn_soft_delete_list_excludes() -> None: ...


@scenario("dal/dynamic-soft-delete.feature", "软删除后计数排除已删除")
def test_dyn_soft_delete_count_excludes() -> None: ...


@scenario("dal/dynamic-soft-delete.feature", "恢复软删除的记录")
def test_dyn_soft_delete_restore() -> None: ...


@scenario("dal/dynamic-soft-delete.feature", "删除不存在的记录返回失败")
def test_dyn_soft_delete_nonexistent() -> None: ...


# ── dynamic-readonly.feature ──


@scenario("dal/dynamic-readonly.feature", "只读表查询正常")
def test_dyn_ro_read() -> None: ...


@scenario("dal/dynamic-readonly.feature", "只读表拒绝创建")
def test_dyn_ro_create() -> None: ...


@scenario("dal/dynamic-readonly.feature", "只读表拒绝更新")
def test_dyn_ro_update() -> None: ...


@scenario("dal/dynamic-readonly.feature", "只读表拒绝删除")
def test_dyn_ro_delete() -> None: ...


@scenario("dal/dynamic-readonly.feature", "只读表拒绝批量创建")
def test_dyn_ro_bulk_create() -> None: ...


# ================================================================
# Base* Protocol Conformance Tests
# ================================================================

from lush_dal_protocol.testing import (
    DtoSyncFullConformanceTests,
)


class TestDynamicSyncDALConformance(DtoSyncFullConformanceTests):
    """验证 DynamicSyncDAL 满足 DtoSyncDAL 协议."""

    @pytest.fixture()
    def dal(self, dyn_session: Session) -> DynamicSyncDAL[_DynDTO, _DynDTO]:  # type: ignore[type-arg]
        return DynamicSyncDAL(TableRef.of("dyn_items", _DynDTO), _DynDTO)

    @pytest.fixture()
    def session(self, dyn_session: Session) -> Session:
        return dyn_session

    @pytest.fixture()
    def sample_cu(self) -> _DynDTO:
        return _DynDTO(name="test")

    @pytest.fixture()
    def make_cu(self) -> Callable[[str], _DynDTO]:
        return lambda label: _DynDTO(name=f"test-{label}")

    def _get_dto_id(self, dto: _DynDTO) -> int:
        assert dto.id is not None
        return dto.id

    def _get_dto_label(self, dto: _DynDTO) -> str:
        return dto.name


# NOTE: DynamicAsyncDAL conformance 需要 aiosqlite + async session,
# 待后续补充 async 专用 conformance 测试.
