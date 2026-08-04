"""BDD 步骤定义 — 同步 DAL + 裸 SQLAlchemy 数据库状态验证.

架构
~~~~

- Given: 通过 DAL 创建测试数据
- When:  通过 DAL 执行业务操作
- Then:  通过裸 SQLAlchemy (sa.text) 直接验证数据库状态, 不依赖 DAL 自身
- 同步 DAL: SyncBaseDAL, 步骤函数均为同步 def

Then 验证策略
~~~~~~~~~~~~~

所有 Then 步骤使用裸 ``session.execute(sa.text(...))`` 查询数据库,
确保验证的是**数据库物理状态**而非 DAL 层的二次解释.
这消除了 "用被测代码验证被测代码" 的循环依赖.

Dal 注册表
~~~~~~~~~~

- "简单CRUD": 无操作人字段、无软删除
- "标准CRUD": 有操作人字段 + 软删除 (is_delete)
- "乐观锁": 有版本号字段 (version=0 起始)
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from typing import Any, ClassVar

import pytest
import sqlalchemy as sa
from pydantic import ConfigDict
from pytest_bdd import given, parsers, then, when
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.pool import NullPool

from lush_sqlalchemyx.base.dal import (
    BaseCU,
    BaseDTO,
    BasicSyncBaseTable,
    DBRetryableError,
    SyncBaseDAL,
    SyncSqlATableBase,
    setup_dal_hooks,
)
from lush_sqlalchemyx.mgrs.mysql.sync_manager import SyncMySQLManager

setup_dal_hooks()

# ════════════════════════════════════════════════════════════════
# 测试数据模型
# ════════════════════════════════════════════════════════════════


class _SimpleTable(BasicSyncBaseTable):
    __tablename__ = "bdd_simple_table"
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)


class _SimpleCU(BaseCU["_SimpleTable"]):
    _Table: ClassVar[type[_SimpleTable]] = _SimpleTable
    name: str


class _SimpleDTO(BaseDTO["_SimpleCU"]):
    _CU: ClassVar[type[_SimpleCU]] = _SimpleCU
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class _SimpleDAL(SyncBaseDAL["_SimpleTable", "_SimpleDTO", "_SimpleCU"]):
    _Table = _SimpleTable
    _DTO = _SimpleDTO
    _CU = _SimpleCU


class _StdTable(BasicSyncBaseTable):
    __tablename__ = "bdd_std_table"
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    value: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    description: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    create_operator_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    update_operator_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True, default=None)
    is_delete: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, default=0)
    update_datetime: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    version: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, default=1, server_default="1")


class _StdCU(BaseCU["_StdTable"]):
    _Table: ClassVar[type[_StdTable]] = _StdTable
    name: str
    value: int = 0
    description: str | None = None
    create_operator_id: int = 0
    update_operator_id: int | None = None


class _StdDTO(BaseDTO["_StdCU"]):
    _CU: ClassVar[type[_StdCU]] = _StdCU
    name: str
    value: int
    model_config = ConfigDict(from_attributes=True)


class _StdDAL(SyncBaseDAL["_StdTable", "_StdDTO", "_StdCU"]):
    _Table = _StdTable
    _DTO = _StdDTO
    _CU = _StdCU


class _VersionTable(BasicSyncBaseTable):
    __tablename__ = "bdd_version_table"
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    value: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    create_operator_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    update_operator_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True, default=None)
    is_delete: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, default=0)
    update_datetime: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    version: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, default=0, server_default="0")


class _VersionCU(BaseCU["_VersionTable"]):
    _Table: ClassVar[type[_VersionTable]] = _VersionTable
    name: str
    value: int = 0
    create_operator_id: int = 0
    update_operator_id: int | None = None


class _VersionDTO(BaseDTO["_VersionCU"]):
    _CU: ClassVar[type[_VersionCU]] = _VersionCU
    name: str
    value: int
    version: int
    model_config = ConfigDict(from_attributes=True)


class _VersionDAL(SyncBaseDAL["_VersionTable", "_VersionDTO", "_VersionCU"]):
    _Table = _VersionTable
    _DTO = _VersionDTO
    _CU = _VersionCU


_ALL_TABLES = [_SimpleTable.__table__, _StdTable.__table__, _VersionTable.__table__]

# ════════════════════════════════════════════════════════════════
# DAL 注册表
# ════════════════════════════════════════════════════════════════

_DAL_META = {
    "简单CRUD": (_SimpleDAL, _SimpleCU, _SimpleTable, False),
    "标准CRUD": (_StdDAL, _StdCU, _StdTable, True),
    "乐观锁": (_VersionDAL, _VersionCU, _VersionTable, True),
}


def _resolve(ctx: dict[str, Any]) -> tuple[type[Any], type[BaseCU[Any]], type[Any], bool]:
    name = ctx.get("current_dal_name", "")
    if name in _DAL_META:
        return _DAL_META[name]  # type: ignore[return-value]
    return (_SimpleDAL, _SimpleCU, _SimpleTable, False)


def _table(ctx: dict[str, Any]) -> type[Any]:
    return _resolve(ctx)[2]


# ════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════


@pytest.fixture
def bdd_context() -> dict[str, Any]:
    return {}


@pytest.fixture
def sync_session() -> Generator[Session, None, None]:
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="bdd_")
    os.close(fd)
    try:
        uri = f"sqlite:///{db_path}"
        manager = SyncMySQLManager(uri, poolclass=NullPool, connect_args={"check_same_thread": False})
        SyncSqlATableBase.metadata.create_all(manager.engine, tables=_ALL_TABLES)
        try:
            with manager.got_manual_session() as session:
                yield session
        finally:
            manager.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


# ════════════════════════════════════════════════════════════════
# 裸 SQLAlchemy 辅助 — Then 用这些验证数据库物理状态
# ════════════════════════════════════════════════════════════════


def _raw_scalar(session: Session, sql: str, params: dict[str, Any] | None = None) -> Any:
    """执行裸 SQL 并返回标量."""
    return session.execute(sa.text(sql), params or {}).scalar()


def _raw_fetchone(session: Session, sql: str, params: dict[str, Any] | None = None) -> Any:
    """执行裸 SQL 并返回第一行 (Row 对象)."""
    return session.execute(sa.text(sql), params or {}).fetchone()


def _raw_rowcount(session: Session, sql: str, params: dict[str, Any] | None = None) -> int:
    """执行裸 SQL 并返回影响行数."""
    result = session.execute(sa.text(sql), params or {})
    return result.rowcount


def _db_count(session: Session, table: type[Any]) -> int:
    """用裸 SQL 统计表中记录数."""
    tname = table.__tablename__
    return _raw_scalar(session, f"SELECT COUNT(*) FROM {tname}")


def _db_count_where(session: Session, table: type[Any], where: str, params: dict[str, Any]) -> int:
    """用裸 SQL 条件统计."""
    tname = table.__tablename__
    return _raw_scalar(session, f"SELECT COUNT(*) FROM {tname} WHERE {where}", params)


def _db_exists(session: Session, table: type[Any], entity_id: int) -> bool:
    tname = table.__tablename__
    return _raw_scalar(session, f"SELECT 1 FROM {tname} WHERE id = :id", {"id": entity_id}) is not None


def _db_col(session: Session, table: type[Any], entity_id: int, col: str) -> Any:
    tname = table.__tablename__
    return _raw_scalar(session, f"SELECT {col} FROM {tname} WHERE id = :id", {"id": entity_id})


# ════════════════════════════════════════════════════════════════
# Given 步骤
# ════════════════════════════════════════════════════════════════


@given(parsers.parse("数据库连接已就绪"))
def given_db_ready(sync_session: Session) -> None:
    pass


@given(parsers.parse('使用 "{dal_name}" 作为当前 DAL'))
def given_select_dal(bdd_context: dict[str, Any], dal_name: str) -> None:
    if dal_name not in _DAL_META:
        raise ValueError(f"未知 DAL: {dal_name!r}, 可用: {list(_DAL_META)}")
    dal_cls = _DAL_META[dal_name][0]
    bdd_context["current_dal"] = dal_cls
    bdd_context["current_dal_name"] = dal_name


def _make_cu(ctx: dict[str, Any], **overrides: Any) -> BaseCU[Any]:
    _, cu_cls, _, needs_op = _resolve(ctx)
    kwargs = dict(overrides)
    if needs_op and "create_operator_id" not in kwargs:
        kwargs["create_operator_id"] = 1
    return cu_cls(**kwargs)  # type: ignore[call-arg]


def _create_record(ctx: dict[str, Any], session: Session, **cu_kw: Any) -> Any:
    dal, _, _, _ = _resolve(ctx)
    cu = _make_cu(ctx, **cu_kw)
    return dal.create(session, cu)


@given(parsers.parse('已存在一条名称为 "{name}" 且值为 "{value:d}" 的记录'))
def given_existing_record_with_value(name: str, value: int, bdd_context: dict[str, Any], sync_session: Session) -> None:
    entity = _create_record(bdd_context, sync_session, name=name, value=value)
    bdd_context["current_entity_id"] = entity.id


@given(parsers.parse('已存在一条名称为 "{name}" 且描述为 "{desc}" 的记录'))
def given_existing_record_with_desc(name: str, desc: str, bdd_context: dict[str, Any], sync_session: Session) -> None:
    entity = _create_record(bdd_context, sync_session, name=name, description=desc)
    bdd_context["current_entity_id"] = entity.id


@given(parsers.parse('已存在一条名称为 "{name}" 的记录'))
def given_existing_record(name: str, bdd_context: dict[str, Any], sync_session: Session) -> None:
    entity = _create_record(bdd_context, sync_session, name=name)
    bdd_context["current_entity_id"] = entity.id


@given(parsers.parse('将该记录的值设置为 "{value:d}"'))
def given_set_value(value: int, bdd_context: dict[str, Any], sync_session: Session) -> None:
    """直接通过裸 SQL 设置字段值，不通过 CU."""
    dal, _, table_cls, _ = _resolve(bdd_context)
    dal.batch_update_by_conditions(
        sync_session,
        whereclause=[table_cls.id == bdd_context["current_entity_id"]],
        update_data={table_cls.value: value},
    )


@given(parsers.parse('将该记录的描述设置为 "{desc}"'))
def given_set_desc(desc: str, bdd_context: dict[str, Any], sync_session: Session) -> None:
    """直接通过裸 SQL 设置字段值."""
    dal, _, table_cls, _ = _resolve(bdd_context)
    dal.batch_update_by_conditions(
        sync_session,
        whereclause=[table_cls.id == bdd_context["current_entity_id"]],
        update_data={table_cls.description: desc},
    )


@given(parsers.parse('已存在一条名称为 "{name1}" 和 "{name2}" 的两条记录'))
def given_two_records(name1: str, name2: str, bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    e1 = dal.create(sync_session, _make_cu(bdd_context, name=name1))
    e2 = dal.create(sync_session, _make_cu(bdd_context, name=name2))
    bdd_context["current_two_ids"] = (e1.id, e2.id)


# ════════════════════════════════════════════════════════════════
# When 步骤
# ════════════════════════════════════════════════════════════════

# ── 基本 CRUD ──


@when(parsers.parse("通过 ID 查询该记录"))
def when_get_by_id(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    bdd_context["op_result"] = dal.get_by_id(sync_session, bdd_context["current_entity_id"])


@when(parsers.parse('查询不存在的记录 ID "{record_id:d}"'))
def when_get_by_id_nonexistent(record_id: int, bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    bdd_context["op_result"] = dal.get_by_id(sync_session, record_id)


@when(parsers.parse('创建一条名称为 "{name}" 的新记录'))
def when_create_record(name: str, bdd_context: dict[str, Any], sync_session: Session) -> None:
    entity = _create_record(bdd_context, sync_session, name=name)
    bdd_context["op_result"] = entity
    bdd_context["current_entity_id"] = entity.id


@when(parsers.parse('创建一条名称为 "{name}" 的记录并返回 DTO'))
def when_create_and_ret_dto(name: str, bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, name=name)
    bdd_context["op_result"] = dal.ret_dto_after_create(sync_session, cu)


@when(parsers.parse('使用新 CU 将记录名称更新为 "{name}"'))
def when_update_record(name: str, bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, name=name)
    bdd_context["op_result"] = dal.update_only_set_by_id(sync_session, bdd_context["current_entity_id"], cu)


@when(parsers.parse('使用新 CU 将记录值更新为 "{value:d}"'))
def when_update_value(value: int, bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, value=value)
    bdd_context["op_result"] = dal.update_only_set_by_id(sync_session, bdd_context["current_entity_id"], cu)


@when(parsers.parse('only-set 更新名称为 "{name}" 且描述置空 (默认 ignore)'))
def when_only_set_ignore_none_desc(name: str, bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, name=name, description=None)
    bdd_context["op_result"] = dal.update_only_set_by_id(sync_session, bdd_context["current_entity_id"], cu)


@when(parsers.parse('only-set 更新名称为 "{name}" 且描述置空 (allow None 策略)'))
def when_only_set_allow_none_desc(name: str, bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, name=name, description=None)
    bdd_context["op_result"] = dal.update_only_set_by_id(sync_session, bdd_context["current_entity_id"], cu, none_policy="allow")


@when("only-set 更新描述置空 (forbid None 策略)")
def when_only_set_forbid_none(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, name="keep", description=None)
    try:
        dal.update_only_set_by_id(sync_session, bdd_context["current_entity_id"], cu, none_policy="forbid")
        bdd_context["_raised"] = None
    except ValueError as e:
        bdd_context["_raised"] = e


@when(parsers.parse("删除该记录"))
def when_delete_record(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    bdd_context["op_result"] = dal.delete_by_id(sync_session, bdd_context["current_entity_id"])


@when(parsers.parse("统计记录总数"))
def when_count(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    bdd_context["op_result"] = dal.count(sync_session)


@when(parsers.parse("检查记录是否存在"))
def when_exists(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    bdd_context["op_result"] = dal.exists(sync_session, bdd_context["current_entity_id"])


# ── 更新: full / partial / none_policy ──


@when(parsers.parse('全量更新记录名称为 "{name}" 值为 "{value:d}"'))
def when_update_full(name: str, value: int, bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, name=name, value=value)
    bdd_context["op_result"] = dal.update_full_by_id(sync_session, bdd_context["current_entity_id"], cu)


@when(parsers.parse('全量更新不存在的记录 ID "{eid:d}"'))
def when_update_full_nonexistent(eid: int, bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, name="ghost")
    bdd_context["op_result"] = dal.update_full_by_id(sync_session, eid, cu)


@when(parsers.parse("部分更新名称和值 (ignore None 策略)"))
def when_update_partial_ignore_none(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, table_cls, _ = _resolve(bdd_context)
    # 用 table column 直接构造 update data, 绕过 CU 校验
    dal.batch_update_by_conditions(
        sync_session,
        whereclause=[table_cls.id == bdd_context["current_entity_id"]],
        update_data={table_cls.value: 99},
    )
    bdd_context["op_result"] = dal.get_by_id(sync_session, bdd_context["current_entity_id"])


@when(parsers.parse('部分更新名称为 "{name}" 且描述置空 (allow None 策略)'))
def when_update_partial_allow_none_desc(name: str, bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, name=name, description=None)
    bdd_context["op_result"] = dal.update_partial_by_id(sync_session, bdd_context["current_entity_id"], cu, none_policy="allow")


@when(parsers.parse("部分更新描述置空 (forbid None 策略)"))
def when_update_partial_forbid_none(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, name="keep", description=None)
    try:
        dal.update_partial_by_id(sync_session, bdd_context["current_entity_id"], cu, none_policy="forbid")
        bdd_context["_raised"] = None
    except ValueError as e:
        bdd_context["_raised"] = e


@when(parsers.parse("部分更新描述置空 (ignore 策略 + 覆盖为 allow)"))
def when_update_partial_override_allow(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, table_cls, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, name="override", description=None)
    bdd_context["op_result"] = dal.update_partial_by_id(
        sync_session,
        bdd_context["current_entity_id"],
        cu,
        none_policy="ignore",
        none_policy_overrides={table_cls.description: "allow"},
    )


@when(parsers.parse('部分更新名称为 "{name}" 并尝试额外更新 description (strict 模式)'))
def when_update_partial_strict_extra(name: str, bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, table_cls, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, name=name, description="should-fail")
    try:
        dal.update_partial_by_id(sync_session, bdd_context["current_entity_id"], cu, fields={table_cls.name}, strict=True)
        bdd_context["_raised"] = None
    except ValueError as e:
        bdd_context["_raised"] = e


@when(parsers.parse('部分更新不存在的记录 ID "{eid:d}"'))
def when_update_partial_nonexistent(eid: int, bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, name="ghost")
    bdd_context["op_result"] = dal.update_partial_by_id(sync_session, eid, cu)


# ── 批量操作 ──


@when(parsers.parse("批量按 ID 查询这两个实体"))
def when_batch_get_entities(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    ids = list(bdd_context["current_two_ids"])
    bdd_context["op_result"] = dal.batch_get_id__entity(sync_session, ids)


@when(parsers.parse("批量按 ID 查询空列表"))
def when_batch_get_empty(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    bdd_context["op_result"] = dal.batch_get_id__entity(sync_session, [])


@when(parsers.parse("批量按 ID 查询并返回 DTO"))
def when_batch_get_dtos(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    bdd_context["op_result"] = dal.batch_get_id__dto(sync_session, [bdd_context["current_entity_id"]])


@when(parsers.parse('批量按 name 字段查询 "{name}"'))
def when_batch_get_field(name: str, bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    bdd_context["op_result"] = dal.batch_get_field__entity(sync_session, field_name="name", field_values=[name])


@when(parsers.parse("批量按 name 字段查询空列表"))
def when_batch_get_field_empty(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    bdd_context["op_result"] = dal.batch_get_field__entity(sync_session, field_name="name", field_values=[])


@when(parsers.parse('批量按 ID 更新值为 "{value:d}"'))
def when_batch_update_by_ids(value: int, bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, table_cls, _ = _resolve(bdd_context)
    bdd_context["_batch_affected"] = dal.batch_update_by_ids(
        sync_session, entity_ids=[bdd_context["current_entity_id"]], update_data={table_cls.value: value}
    )


@when(parsers.parse("批量按 ID 更新空列表"))
def when_batch_update_empty(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, table_cls, _ = _resolve(bdd_context)
    bdd_context["_batch_affected"] = dal.batch_update_by_ids(sync_session, entity_ids=[], update_data={table_cls.value: 99})


@when(parsers.parse('批量按当前实体 ID 条件更新名称为 "{name}"'))
def when_batch_update_by_conditions(name: str, bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, table_cls, _ = _resolve(bdd_context)
    dal.batch_update_by_conditions(
        sync_session, whereclause=[table_cls.id == bdd_context["current_entity_id"]], update_data={table_cls.name: name}
    )
    bdd_context["op_result"] = dal.get_by_id(sync_session, bdd_context["current_entity_id"])


@when(parsers.parse('批量按 ID 条件更新值为 "{value:d}"'))
def when_batch_update_conditions_value(value: int, bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, table_cls, _ = _resolve(bdd_context)
    dal.batch_update_by_conditions(
        sync_session, whereclause=[table_cls.id == bdd_context["current_entity_id"]], update_data={table_cls.value: value}
    )
    bdd_context["op_result"] = dal.get_by_id(sync_session, bdd_context["current_entity_id"])


@when(parsers.parse("批量按无效 key 更新"))
def when_batch_update_invalid_key(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, table_cls, _ = _resolve(bdd_context)
    try:
        dal.batch_update_by_conditions(sync_session, whereclause=[table_cls.id == bdd_context["current_entity_id"]], update_data={123: 77})
        bdd_context["_raised"] = None
    except ValueError as e:
        bdd_context["_raised"] = e


# ── 只读保护 ──


@when(parsers.parse('尝试在只读会话中更新记录名称为 "{name}"'))
def when_update_in_readonly_session(name: str, bdd_context: dict[str, Any], sync_session: Session) -> None:
    from lush_sqlalchemyx.base.dal._common import READONLY_SESSION_FLAG

    sync_session.info[READONLY_SESSION_FLAG] = True
    dal, _, _, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, name=name)
    try:
        dal.update_only_set_by_id(sync_session, bdd_context["current_entity_id"], cu)
        bdd_context["_op_blocked"] = False
    except TypeError:
        bdd_context["_op_blocked"] = True


@when(parsers.parse("尝试在只读会话中全量更新"))
def when_full_update_in_readonly(bdd_context: dict[str, Any], sync_session: Session) -> None:
    from lush_sqlalchemyx.base.dal._common import READONLY_SESSION_FLAG

    sync_session.info[READONLY_SESSION_FLAG] = True
    dal, _, _, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, name="ro-fail", value=0)
    try:
        dal.update_full_by_id(sync_session, bdd_context["current_entity_id"], cu)
        bdd_context["_op_blocked"] = False
    except TypeError:
        bdd_context["_op_blocked"] = True


@when(parsers.parse("尝试在只读会话中部分更新"))
def when_partial_update_in_readonly(bdd_context: dict[str, Any], sync_session: Session) -> None:
    from lush_sqlalchemyx.base.dal._common import READONLY_SESSION_FLAG

    sync_session.info[READONLY_SESSION_FLAG] = True
    dal, _, _, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, name="ro-fail")
    try:
        dal.update_partial_by_id(sync_session, bdd_context["current_entity_id"], cu)
        bdd_context["_op_blocked"] = False
    except TypeError:
        bdd_context["_op_blocked"] = True


@when(parsers.parse("尝试在只读会话中删除"))
def when_delete_in_readonly(bdd_context: dict[str, Any], sync_session: Session) -> None:
    from lush_sqlalchemyx.base.dal._common import READONLY_SESSION_FLAG

    sync_session.info[READONLY_SESSION_FLAG] = True
    dal, _, _, _ = _resolve(bdd_context)
    try:
        dal.delete_by_id(sync_session, bdd_context["current_entity_id"])
        bdd_context["_op_blocked"] = False
    except TypeError:
        bdd_context["_op_blocked"] = True


@when(parsers.parse("尝试在只读会话中批量更新"))
def when_batch_update_in_readonly(bdd_context: dict[str, Any], sync_session: Session) -> None:
    from lush_sqlalchemyx.base.dal._common import READONLY_SESSION_FLAG

    sync_session.info[READONLY_SESSION_FLAG] = True
    dal, _, table_cls, _ = _resolve(bdd_context)
    try:
        dal.batch_update_by_conditions(
            sync_session,
            whereclause=[table_cls.id == bdd_context["current_entity_id"]],
            update_data={table_cls.value: 1},
        )
        bdd_context["_op_blocked"] = False
    except TypeError:
        bdd_context["_op_blocked"] = True


@when(parsers.parse("尝试在只读会话中乐观锁更新"))
def when_optlock_in_readonly(bdd_context: dict[str, Any], sync_session: Session) -> None:
    from lush_sqlalchemyx.base.dal._common import READONLY_SESSION_FLAG

    sync_session.info[READONLY_SESSION_FLAG] = True
    dal, _, _, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, name="ro-opt-fail")
    try:
        dal.update_only_set_with_optimistic_lock(sync_session, bdd_context["current_entity_id"], cu, expected_version=0)
        bdd_context["_op_blocked"] = False
    except TypeError:
        bdd_context["_op_blocked"] = True


# ── 迭代器 ──


@when(parsers.parse("迭代遍历全部记录"))
def when_iter_all(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    bdd_context["op_result"] = list(dal.iter_records(sync_session))


@when(parsers.parse("迭代遍历全部记录 (含已删除)"))
def when_iter_with_deleted(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    bdd_context["op_result"] = list(dal.iter_records(sync_session, with_deleted=True))


@when(parsers.parse('按名称 "{name}" 条件迭代遍历'))
def when_iter_with_where(name: str, bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, table_cls, _ = _resolve(bdd_context)
    bdd_context["op_result"] = list(dal.iter_records(sync_session, where_clauses=[table_cls.name == name]))


@when(parsers.parse("迭代遍历返回 DTO"))
def when_iter_dtos(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    bdd_context["op_result"] = list(dal.iter_record_dtos(sync_session))


# ── 乐观锁 ──


@when(parsers.parse("乐观锁更新名称和值 (期望版本 0)"))
def when_optlock_update(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, name="opt-updated", value=20)
    bdd_context["op_result"] = dal.update_only_set_with_optimistic_lock(
        sync_session, bdd_context["current_entity_id"], cu, expected_version=0
    )


@when(parsers.parse("乐观锁更新 (期望错误版本 999)"))
def when_optlock_wrong_version(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, name="conflict")
    try:
        dal.update_only_set_with_optimistic_lock(sync_session, bdd_context["current_entity_id"], cu, expected_version=999)
        bdd_context["_raised"] = None
    except DBRetryableError as e:
        bdd_context["_raised"] = e


@when(parsers.parse('乐观锁更新不存在的记录 ID "{eid:d}"'))
def when_optlock_nonexistent(eid: int, bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, name="nope")
    try:
        dal.update_only_set_with_optimistic_lock(sync_session, eid, cu, expected_version=0)
        bdd_context["_raised"] = None
    except DBRetryableError as e:
        bdd_context["_raised"] = e


@when(parsers.parse("乐观锁空更新"))
def when_optlock_empty_update(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, name="opt-empty-keep")
    bdd_context["op_result"] = dal.update_only_set_with_optimistic_lock(
        sync_session, bdd_context["current_entity_id"], cu, expected_version=0
    )


@when(parsers.parse("乐观锁更新并 refresh"))
def when_optlock_with_refresh(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    cu = _make_cu(bdd_context, name="opt-refreshed")
    bdd_context["op_result"] = dal.update_only_set_with_optimistic_lock(
        sync_session, bdd_context["current_entity_id"], cu, expected_version=0, need_refresh=True
    )


@when(parsers.parse("使用简单 DAL 乐观锁更新 (无 version 字段)"))
def when_optlock_no_version_field(bdd_context: dict[str, Any], sync_session: Session) -> None:
    simple_dal = _SimpleDAL
    cu = _SimpleCU(name="no-version-update")
    try:
        simple_dal.update_only_set_with_optimistic_lock(sync_session, bdd_context["current_entity_id"], cu, expected_version=0)
        bdd_context["_raised"] = None
    except AttributeError as e:
        bdd_context["_raised"] = e


# ── 悲观锁 ──


@when(parsers.parse("通过 ID 加悲观锁查询该记录"))
def when_get_by_id_for_update(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    bdd_context["op_result"] = dal.get_by_id_for_update(sync_session, bdd_context["current_entity_id"])


@when(parsers.parse("批量加悲观锁查询这两个 ID"))
def when_batch_get_for_update(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    ids = list(bdd_context["current_two_ids"])
    bdd_context["op_result"] = dal.batch_get_for_update(sync_session, ids)


@when(parsers.parse("批量加悲观锁查询空列表"))
def when_batch_get_for_update_empty(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    bdd_context["op_result"] = dal.batch_get_for_update(sync_session, [])


@when(parsers.parse("按条件加悲观锁查询单条记录"))
def when_get_one_for_update(bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, table_cls, _ = _resolve(bdd_context)
    bdd_context["op_result"] = dal.get_one_for_update(sync_session, where_clauses=[table_cls.id == bdd_context["current_entity_id"]])


# ── SQL 执行 / 事务 / 重试 ──


@when(parsers.parse('执行裸 SQL: "{sql}"'))
def when_execute_sql(sql: str, bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    bdd_context["op_result"] = dal.execute_sql(sync_session, sql)


@when(parsers.parse('执行只读 SQL: "{sql}"'))
def when_execute_readonly_sql(sql: str, bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    bdd_context["op_result"] = dal.execute_readonly_sql(sync_session, sql)


@when(parsers.parse('执行写入 SQL: "{sql}"'))
def when_execute_write_sql_readonly(sql: str, bdd_context: dict[str, Any], sync_session: Session) -> None:
    dal, _, _, _ = _resolve(bdd_context)
    try:
        dal.execute_readonly_sql(sync_session, sql)
        bdd_context["_raised"] = None
    except RuntimeError as e:
        bdd_context["_raised"] = e


@when(parsers.parse("使用 sync_with_retry 执行会成功重试的操作"))
def when_retry_success(bdd_context: dict[str, Any], sync_session: Session) -> None:
    from lush_sqlalchemyx.base.dal._common import RetryConfig
    from lush_sqlalchemyx.base.dal._sync import sync_with_retry

    call_count = [0]

    @sync_with_retry(RetryConfig(max_attempts=3, initial_delay=0.001, max_delay=0.01))
    def _op() -> str:
        call_count[0] += 1
        if call_count[0] < 2:
            raise DBRetryableError("conflict")
        return "ok"

    bdd_context["op_result"] = _op()
    bdd_context["_retry_count"] = call_count[0]


@when(parsers.parse("使用 sync_with_retry 执行总是失败的操作"))
def when_retry_exhausted(bdd_context: dict[str, Any], sync_session: Session) -> None:
    from lush_sqlalchemyx.base.dal._common import RetryConfig
    from lush_sqlalchemyx.base.dal._sync import sync_with_retry

    @sync_with_retry(RetryConfig(max_attempts=2, initial_delay=0.001, max_delay=0.01))
    def _fail() -> str:
        raise DBRetryableError("always conflict")

    try:
        _fail()
        bdd_context["_raised"] = None
    except DBRetryableError as e:
        bdd_context["_raised"] = e


# ════════════════════════════════════════════════════════════════
# Then 步骤 ⚠ 全部使用裸 SQLAlchemy 验证数据库物理状态
# ════════════════════════════════════════════════════════════════


def _get_result(ctx: dict[str, Any]) -> Any:
    if "op_result" not in ctx:
        raise RuntimeError("bdd_context 中没有 'op_result'")
    return ctx["op_result"]


def _parse_expected_scalar(expected: str) -> int | float | str:
    """将 BDD 期望字符串尽量解析为 int/float, 失败则保留原字符串."""
    try:
        return int(expected)
    except ValueError:
        pass
    try:
        return float(expected)
    except ValueError:
        return expected


def _assert_loose_equals(actual: Any, expected: str, *, detail: str | None = None) -> None:
    """比较实际值与期望字符串 (支持数字字面量松散匹配)."""
    parsed = _parse_expected_scalar(expected)
    if isinstance(parsed, str):
        if detail:
            assert str(actual) == expected, detail
        else:
            assert str(actual) == expected
        return
    if detail:
        assert actual == parsed, detail
    else:
        assert actual == parsed


# ── 实体/DTO 断言 (轻量, 对象层面) ──


@then("返回的实体不为空")
def then_result_not_none(bdd_context: dict[str, Any]) -> None:
    assert _get_result(bdd_context) is not None


@then("返回的实体为空")
def then_result_is_none_obj(bdd_context: dict[str, Any]) -> None:
    assert _get_result(bdd_context) is None


@then(parsers.parse('返回的实体名称应为 "{expected_name}"'))
def then_entity_name_is(bdd_context: dict[str, Any], expected_name: str) -> None:
    r = _get_result(bdd_context)
    assert r is not None
    assert r.name == expected_name


@then(parsers.parse('返回的实体的 "{field}" 应为 "{expected_value}"'))
def then_entity_field_equals(bdd_context: dict[str, Any], field: str, expected_value: str) -> None:
    r = _get_result(bdd_context)
    assert r is not None, f"实体 None, 无法验证 {field}"
    assert hasattr(r, field), f"无 {field!r} 字段"
    _assert_loose_equals(getattr(r, field), expected_value)


@then("返回的结果为 True")
def then_result_true(bdd_context: dict[str, Any]) -> None:
    assert _get_result(bdd_context) is True


@then("返回的结果为 False")
def then_result_false(bdd_context: dict[str, Any]) -> None:
    assert _get_result(bdd_context) is False


@then("返回的结果为空")
def then_result_empty(bdd_context: dict[str, Any]) -> None:
    r = _get_result(bdd_context)
    if isinstance(r, dict):
        assert len(r) == 0, f"期望空字典: {r!r}"
    elif isinstance(r, (list, tuple)):
        assert len(r) == 0, f"期望空列表: {r!r}"
    else:
        assert r is None, f"期望 None/空, 实际: {r!r}"


@then("返回的结果不为空")
def then_result_not_empty(bdd_context: dict[str, Any]) -> None:
    r = _get_result(bdd_context)
    assert r is not None, "结果为 None"
    if isinstance(r, dict):
        assert len(r) > 0, f"空字典: {r!r}"
    elif isinstance(r, (list, tuple)):
        assert len(r) > 0, f"空列表: {r!r}"


@then("操作被阻止")
def then_operation_blocked(bdd_context: dict[str, Any]) -> None:
    assert bdd_context.get("_op_blocked") is True


@then(parsers.parse("抛出了 {exc_name}"))
def then_exception_raised(bdd_context: dict[str, Any], exc_name: str) -> None:
    e = bdd_context.get("_raised")
    assert e is not None, f"期望抛出 {exc_name}, 但未抛出"
    assert exc_name in type(e).__name__, f"期望 {exc_name}, 实际 {type(e).__name__}: {e}"


@then("没有抛出异常")
def then_no_exception(bdd_context: dict[str, Any]) -> None:
    assert bdd_context.get("_raised") is None, f"意外抛出: {bdd_context['_raised']}"


@then("返回的结果为 True (布尔)")
def then_result_bool_true(bdd_context: dict[str, Any]) -> None:
    assert _get_result(bdd_context) is True


# ── ⚠ 裸 SQLAlchemy 数据库状态验证 ──


@then(parsers.parse('数据库表中存在名称为 "{name}" 的记录'))
def then_db_has_record(bdd_context: dict[str, Any], sync_session: Session, name: str) -> None:
    table = _table(bdd_context)
    cnt = _db_count_where(sync_session, table, "name = :name", {"name": name})
    assert cnt >= 1, f"数据库中不存在 name={name!r} 的记录"


@then(parsers.parse('数据库表中不存在 ID 为 "{eid:d}" 的记录'))
def then_db_no_record_by_id(bdd_context: dict[str, Any], sync_session: Session, eid: int) -> None:
    table = _table(bdd_context)
    assert not _db_exists(sync_session, table, eid), f"数据库中存在 id={eid} 的记录"


@then("数据库表中该记录已不存在")
def then_db_record_gone(bdd_context: dict[str, Any], sync_session: Session) -> None:
    table = _table(bdd_context)
    eid = bdd_context["current_entity_id"]
    assert not _db_exists(sync_session, table, eid), f"id={eid} 仍存在"


@then(parsers.parse('数据库表中 ID 为当前实体 ID 的记录的 "{col}" 应为 "{expected}"'))
def then_db_col_equals(bdd_context: dict[str, Any], sync_session: Session, col: str, expected: str) -> None:
    table = _table(bdd_context)
    eid = bdd_context["current_entity_id"]
    actual = _db_col(sync_session, table, eid, col)
    _assert_loose_equals(actual, expected, detail=f"DB: {col}={actual!r}, 期望 {expected!r}")


@then(parsers.parse("数据库表中记录总数为 {count:d}"))
def then_db_count_exact(bdd_context: dict[str, Any], sync_session: Session, count: int) -> None:
    table = _table(bdd_context)
    actual = _db_count(sync_session, table)
    assert actual == count, f"期望 {count} 条, 实际 {actual} 条"


@then(parsers.parse("数据库表中记录总数至少为 {min_count:d}"))
def then_db_count_at_least(bdd_context: dict[str, Any], sync_session: Session, min_count: int) -> None:
    table = _table(bdd_context)
    actual = _db_count(sync_session, table)
    assert actual >= min_count, f"期望 >= {min_count}, 实际 {actual}"


@then("数据库表中 is_delete 为 1")
def then_db_is_delete_one(bdd_context: dict[str, Any], sync_session: Session) -> None:
    table = _table(bdd_context)
    eid = bdd_context["current_entity_id"]
    val = _db_col(sync_session, table, eid, "is_delete")
    assert val == 1, f"期望 is_delete=1, 实际={val}"


@then(parsers.parse("数据库表中 version 为 {ver:d}"))
def then_db_version_is(bdd_context: dict[str, Any], sync_session: Session, ver: int) -> None:
    table = _table(bdd_context)
    eid = bdd_context["current_entity_id"]
    val = _db_col(sync_session, table, eid, "version")
    assert val == ver, f"期望 version={ver}, 实际={val}"


@then(parsers.parse("受影响行数为 {n:d}"))
def then_affected_rows(bdd_context: dict[str, Any], n: int) -> None:
    actual = bdd_context.get("_batch_affected")
    assert actual == n, f"期望受影响行数={n}, 实际={actual}"


@then(parsers.parse("遍历结果至少有 {min_count:d} 条"))
def then_iter_count_at_least(bdd_context: dict[str, Any], min_count: int) -> None:
    r = _get_result(bdd_context)
    assert isinstance(r, (list, tuple)), f"期望列表, 实际: {type(r)}"
    assert len(r) >= min_count


@then("遍历结果包含已删除记录")
def then_iter_contains_deleted(bdd_context: dict[str, Any]) -> None:
    r = _get_result(bdd_context)
    ids = {getattr(x, "id", None) for x in r}
    assert bdd_context["current_entity_id"] in ids, "遍历结果不包含已删除记录"


@then("删除后查询结果为空")
def then_after_delete_not_found(bdd_context: dict[str, Any], sync_session: Session) -> None:
    table = _table(bdd_context)
    assert not _db_exists(sync_session, table, bdd_context["current_entity_id"])


@then(parsers.parse("返回的记录总数至少为 {min_count:d}"))
def then_count_at_least(bdd_context: dict[str, Any], min_count: int) -> None:
    r = _get_result(bdd_context)
    assert isinstance(r, int)
    assert r >= min_count


@then(parsers.parse('返回的 DTO 名称应为 "{expected_name}"'))
def then_dto_name_is(bdd_context: dict[str, Any], expected_name: str) -> None:
    r = _get_result(bdd_context)
    assert r is not None
    assert r.name == expected_name
