#!/usr/bin/env python3
"""lush-sqlalchemyx 软删 issue 最小复现（自包含单文件，SQLite :memory:）。

依赖: lush-sqlalchemyx>=0.3.2, sqlalchemy>=2.0, pydantic>=2

用法（在本目录或任意路径）::

    python repro.py positive          # 问题1: 钩子已注册时 get_by_id 与 select 不一致
    python repro.py hooks-missing     # 问题2: 钩子未注册 → 物理删除（严重）
    python repro.py no-select-filter  # 问题2b: 无 SELECT 过滤 → is_delete=1 仍可见
    python repro.py all               # 依次运行以上场景

退出码 0 = 观测到 issue 描述的行为；非 0 = 未复现或环境异常。

说明: SQLite 足以复现 ORM 语义问题；合并修复前请在目标 MySQL + Flask-SQLAlchemy 环境复测。
"""

from __future__ import annotations

import argparse
from typing import ClassVar

import sqlalchemy as sa
from lush_sqlalchemyx.base.dal import BaseCU, BaseDTO, SoftDeleteTableMixin, SyncBaseDAL
from pydantic import ConfigDict
from sqlalchemy import event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.orm import Session as SyncSession

# 加载 lush 模块即注册钩子（当前 lush 行为）；反例场景会显式 unregister
import lush_sqlalchemyx.base.dal._common as _lush_dal_common  # noqa: F401

TABLE = "lush_issue_demo_soft_delete_item"


# ---------------------------------------------------------------------------
# 钩子 register / unregister（模拟「用户未初始化 lush」）
# ---------------------------------------------------------------------------


def _listeners() -> tuple[tuple[str, object], ...]:
    return (
        ("before_flush", _lush_dal_common.__receive_before_flush),
        ("do_orm_execute", _lush_dal_common.__add_filtering_criteria),
    )


def hooks_status() -> dict[str, bool]:
    return {name: event.contains(SyncSession, name, fn) for name, fn in _listeners()}


def register_hooks() -> None:
    for name, fn in _listeners():
        if not event.contains(SyncSession, name, fn):
            event.listen(SyncSession, name, fn, insert=True)


def unregister_hooks() -> None:
    for name, fn in _listeners():
        if event.contains(SyncSession, name, fn):
            event.remove(SyncSession, name, fn)


# ---------------------------------------------------------------------------
# 最小 ORM / DAL
# ---------------------------------------------------------------------------


class _Base(DeclarativeBase):
    pass


class _Item(SoftDeleteTableMixin, _Base):
    __tablename__ = TABLE

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(32), nullable=False, default="")


class _CU(BaseCU[_Item]):
    _Table: ClassVar[type[_Item]] = _Item
    name: str = "demo"


class _DTO(_CU, BaseDTO[_CU]):
    _CU: ClassVar[type[_CU]] = _CU
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)
    id: int


class _DAL(SyncBaseDAL[_Item, _DTO, _CU]):
    _Table: ClassVar[type[_Item]] = _Item
    _DTO: ClassVar[type[_DTO]] = _DTO


def _session() -> tuple[Session, sa.Engine]:
    engine = sa.create_engine("sqlite:///:memory:")
    _Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)(), engine


def _sql_count(session: Session, row_id: int) -> int:
    return int(
        session.execute(
            sa.text(f"SELECT COUNT(*) FROM `{TABLE}` WHERE id = :id"), {"id": row_id}
        ).scalar_one()
    )


def _sql_is_delete(session: Session, row_id: int) -> int | None:
    v = session.execute(
        sa.text(f"SELECT is_delete FROM `{TABLE}` WHERE id = :id"), {"id": row_id}
    ).scalar_one_or_none()
    return None if v is None else int(v)


def _observe(session: Session, row_id: int) -> dict[str, object]:
    return {
        "hooks": hooks_status(),
        "sql_row_count": _sql_count(session, row_id),
        "sql_is_delete": _sql_is_delete(session, row_id),
        "orm_select_ids": [
            int(r.id) for r in session.execute(sa.select(_Item)).scalars()
        ],
        "dal_get_all_ids": [d.id for d in _DAL.get_all(session, limit=20)],
        "session_get_hit": session.get(_Item, row_id) is not None,
        "dal_get_by_id_hit": _DAL.get_by_id(session, row_id) is not None,
        "dal_exists": _DAL.exists(session, row_id),
    }


# ---------------------------------------------------------------------------
# 场景
# ---------------------------------------------------------------------------


def scenario_positive() -> int:
    """钩子已注册：软删留存 + get 路径与 list/select 不一致。"""
    print("=== scenario: positive (hooks on, session.get vs select) ===")
    register_hooks()
    print("hooks:", hooks_status())

    session, engine = _session()
    try:
        ent = _DAL.create(session, _CU(name="positive"))
        session.flush()
        rid = ent.id
        _DAL.delete_by_id(session, rid)
        session.flush()
        obs = _observe(session, rid)
        print("observations:", obs)

        ok = (
            obs["sql_is_delete"] == 1
            and obs["sql_row_count"] == 1
            and obs["session_get_hit"]
            and obs["dal_get_by_id_hit"]
            and obs["dal_exists"]
            and rid not in obs["orm_select_ids"]
            and rid not in obs["dal_get_all_ids"]
        )
        print("RESULT:", "REPRODUCED" if ok else "NOT REPRODUCED")
        return 0 if ok else 1
    finally:
        session.close()
        engine.dispose()


def scenario_hooks_missing() -> int:
    """钩子未注册：delete_by_id 物理删除，无异常。"""
    print("=== scenario: hooks-missing (physical DELETE) ===")
    unregister_hooks()
    print("hooks:", hooks_status())

    session, engine = _session()
    try:
        ent = _DAL.create(session, _CU(name="hooks-missing"))
        session.flush()
        rid = ent.id
        _DAL.delete_by_id(session, rid)
        session.flush()
        obs = _observe(session, rid)
        print("observations:", obs)

        ok = obs["sql_row_count"] == 0 and obs["sql_is_delete"] is None
        print(
            "RESULT:", "REPRODUCED (silent data loss risk)" if ok else "NOT REPRODUCED"
        )
        return 0 if ok else 1
    finally:
        session.close()
        engine.dispose()
        register_hooks()


def scenario_no_select_filter() -> int:
    """仅注销 do_orm_execute：库内 is_delete=1 但 select/get_all 仍可见。"""
    print("=== scenario: no-select-filter (is_delete=1 still in ORM lists) ===")
    register_hooks()
    unregister_hooks()
    # 只恢复 before_flush，保留软删写入
    event.listen(
        SyncSession,
        "before_flush",
        _lush_dal_common.__receive_before_flush,
        insert=True,
    )
    print("hooks:", hooks_status())

    session, engine = _session()
    try:
        ent = _DAL.create(session, _CU(name="no-filter"))
        session.flush()
        rid = ent.id
        ent.is_delete = 1
        session.flush()

        obs = _observe(session, rid)
        print("observations:", obs)

        ok = (
            obs["sql_is_delete"] == 1
            and rid in obs["orm_select_ids"]
            and rid in obs["dal_get_all_ids"]
        )
        print("RESULT:", "REPRODUCED" if ok else "NOT REPRODUCED")
        return 0 if ok else 1
    finally:
        session.close()
        engine.dispose()
        register_hooks()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "scenario",
        nargs="?",
        default="all",
        choices=("positive", "hooks-missing", "no-select-filter", "all"),
        help="复现场景（默认 all）",
    )
    args = parser.parse_args(argv)

    runners = {
        "positive": scenario_positive,
        "hooks-missing": scenario_hooks_missing,
        "no-select-filter": scenario_no_select_filter,
    }
    if args.scenario == "all":
        codes = [fn() for fn in runners.values()]
        return 0 if all(c == 0 for c in codes) else 1
    return runners[args.scenario]()


if __name__ == "__main__":
    raise SystemExit(main())
