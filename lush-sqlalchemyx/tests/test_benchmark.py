"""DAL 性能基准测试.

使用 pytest-benchmark 对核心 DAL 操作建立性能基线.
运行: just bench
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any, ClassVar

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.pool import NullPool

from lush_sqlalchemyx.base.dal import BaseCU, BaseDTO, BasicAsyncBaseTable, SyncBaseDAL

# ─── Test Models ──────────────────────────────────────────────


class _BenchTable(BasicAsyncBaseTable):
    __tablename__ = "bench_table_sync"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    version: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, default=1)


class _BenchCU(BaseCU["_BenchTable"]):
    _Table: ClassVar[type] = _BenchTable
    name: str = "bench"


class _BenchDTO(BaseDTO["_BenchCU"]):
    _CU: ClassVar[type] = _BenchCU
    id: int
    name: str = ""


class _BenchDAL(SyncBaseDAL["_BenchTable", "_BenchCU", "_BenchDTO"]):
    _Table = _BenchTable
    _DTO = _BenchDTO


# ─── Fixtures ─────────────────────────────────────────────────


@pytest.fixture(scope="module")
def sync_engine(mysql_endpoint: Any) -> Generator[Any, None, None]:
    url = mysql_endpoint.sqlalchemy_url.replace("+aiomysql", "+pymysql")
    eng = create_engine(url, poolclass=NullPool, echo=False)
    _BenchTable.metadata.create_all(eng)
    yield eng
    _BenchTable.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def sync_session(sync_engine: Any) -> Generator[Session, None, None]:
    with Session(sync_engine, expire_on_commit=False) as sess:
        with sess.begin():
            yield sess
            sess.rollback()


# ─── Benchmarks ───────────────────────────────────────────────


@pytest.mark.benchmark(group="create")
def test_bench_create(benchmark: Any, sync_session: Session) -> None:
    """基准: 单次 create 操作."""
    benchmark(_BenchDAL.create, sync_session, _BenchCU(name="bench-create"))


@pytest.mark.benchmark(group="read")
def test_bench_get_by_id(benchmark: Any, sync_session: Session) -> None:
    """基准: 单次 get_by_id 操作."""
    entity = _BenchDAL.create(sync_session, _BenchCU(name="bench-read"))
    benchmark(_BenchDAL.get_by_id, sync_session, entity.id)


@pytest.mark.benchmark(group="read")
def test_bench_count(benchmark: Any, sync_session: Session) -> None:
    """基准: count 操作."""
    _BenchDAL.create(sync_session, _BenchCU(name="bench-count"))
    benchmark(_BenchDAL.count, sync_session)


@pytest.mark.benchmark(group="update")
def test_bench_update(benchmark: Any, sync_session: Session) -> None:
    """基准: 单次 update_only_set_by_id 操作."""
    entity = _BenchDAL.create(sync_session, _BenchCU(name="bench-update"))
    benchmark(_BenchDAL.update_only_set_by_id, sync_session, entity.id, _BenchCU(name="updated"))


@pytest.mark.benchmark(group="delete")
def test_bench_delete(benchmark: Any, sync_session: Session) -> None:
    """基准: 单次 delete_by_id 操作."""
    entity = _BenchDAL.create(sync_session, _BenchCU(name="bench-del"))
    benchmark(_BenchDAL.delete_by_id, sync_session, entity.id)


@pytest.mark.benchmark(group="batch")
def test_bench_batch_get_id__entity(benchmark: Any, sync_session: Session) -> None:
    """基准: batch_get_id__entity (10 条) 操作."""
    ids = [_BenchDAL.create(sync_session, _BenchCU(name=f"batch-{i}")).id for i in range(10)]
    benchmark(_BenchDAL.batch_get_id__entity, sync_session, ids)


@pytest.mark.benchmark(group="dto")
def test_bench_ret_dto(benchmark: Any, sync_session: Session) -> None:
    """基准: ret_dto_after_get_by_id 操作."""
    entity = _BenchDAL.create(sync_session, _BenchCU(name="bench-dto"))
    benchmark(_BenchDAL.ret_dto_after_get_by_id, sync_session, entity.id)


@pytest.mark.benchmark(group="lock")
def test_bench_get_for_update(benchmark: Any, sync_session: Session) -> None:
    """基准: get_by_id_for_update (悲观锁) 操作."""
    entity = _BenchDAL.create(sync_session, _BenchCU(name="bench-lock"))
    benchmark(_BenchDAL.get_by_id_for_update, sync_session, entity.id)


@pytest.mark.benchmark(group="lock")
def test_bench_optimistic_lock(benchmark: Any, sync_session: Session) -> None:
    """基准: update_only_set_with_optimistic_lock (乐观锁) 操作."""
    entity = _BenchDAL.create(sync_session, _BenchCU(name="bench-opt"))

    state = {"version": entity.version}

    def _run() -> None:
        result = _BenchDAL.update_only_set_with_optimistic_lock(
            sync_session,
            entity.id,
            _BenchCU(name="opt-update"),
            expected_version=state["version"],
        )
        if result:
            state["version"] = result.version

    benchmark(_run)
