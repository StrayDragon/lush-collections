"""同步 MySQL 管理器 — ``manager.py`` 的同步镜像."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager, suppress
from typing import Any

import sqlalchemy as sa
from sqlalchemy import CursorResult, TextClause, create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session, sessionmaker

from lush_sqlalchemyx.base.dal._common import READONLY_SESSION_FLAG


class SyncMySQLManager:
    """同步数据库管理器"""

    def __init__(self, database_url: str, **engine_kwargs: Any) -> None:
        default_kwargs: dict[str, Any] = {
            "pool_size": 20,
            "max_overflow": 30,
            "pool_pre_ping": True,
            "pool_recycle": 3600,
            "echo": False,
        }

        final_kwargs = default_kwargs.copy()

        if "poolclass" in engine_kwargs:
            for key in ("pool_size", "max_overflow", "pool_recycle"):
                _ = final_kwargs.pop(key, None)

        final_kwargs.update(engine_kwargs)

        self.engine: Engine = create_engine(
            database_url,
            **final_kwargs,
        )

        self.session_local: sessionmaker[Session] = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )

    @classmethod
    def from_engine(cls, engine: Engine, **session_kwargs: Any) -> SyncMySQLManager:
        """从已有 Engine 创建管理器（兼容 Flask-SQLAlchemy 等场景）."""
        instance = object.__new__(cls)
        instance.engine = engine
        defaults: dict[str, Any] = {
            "bind": engine,
            "autoflush": False,
            "expire_on_commit": False,
        }
        defaults.update(session_kwargs)
        instance.session_local = sessionmaker(**defaults)
        return instance

    @contextmanager
    def got_manual_session(self) -> Generator[Session, None, None]:
        session = self.session_local()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @contextmanager
    def got_soft_impl_auto_commit_session(self) -> Generator[Session, None, None]:
        session = self.session_local()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @contextmanager
    def got_readonly_session(self) -> Generator[Session, None, None]:
        session = self.session_local()
        session.info[READONLY_SESSION_FLAG] = True
        try:
            with suppress(Exception):
                _ = session.execute(sa.text("SET TRANSACTION READ ONLY"))
            yield session
            session.rollback()
        except Exception:
            session.rollback()
            raise
        finally:
            try:
                session.info.pop(READONLY_SESSION_FLAG, None)
            finally:
                session.close()

    def health_check(self) -> bool:
        try:
            with self.got_manual_session() as session:
                _ = session.execute(sa.text("SELECT 1"))
                return True
        except Exception:
            return False

    def close(self) -> None:
        self.engine.dispose()

    def execute_sql(
        self,
        sql_text: str | TextClause,
        params: dict[str, Any] | list[dict[str, Any]] | None = None,
        execution_options: dict[str, Any] | None = None,
    ) -> sa.Result[Any]:
        with self.engine.connect() as conn:
            result = execute_sql(conn, sql_text, params, execution_options)
            frozen = result.freeze()
            conn.commit()
            return frozen()


def execute_sql(
    conn: Connection,
    sql_text: str | TextClause,
    params: dict[str, Any] | list[dict[str, Any]] | None = None,
    execution_options: dict[str, Any] | None = None,
) -> CursorResult[Any]:
    if params is None:
        params = {}

    stmt = sql_text if isinstance(sql_text, TextClause) else text(sql_text)

    return conn.execute(stmt, params, execution_options=execution_options)


@contextmanager
def configured_session_temporarily(
    session: Session,
    *,
    autoflush: bool | None = None,
    autocommit: bool | None = None,
) -> Generator[Session, None, None]:
    original_autoflush = session.autoflush
    changed_autoflush = False

    try:
        if autoflush is not None and original_autoflush != autoflush:
            session.autoflush = autoflush
            changed_autoflush = True

        yield session

        if autocommit is True:
            session.commit()

    except Exception:
        session.rollback()
        raise
    finally:
        if changed_autoflush:
            session.autoflush = original_autoflush


def must_rollback_if_in_transaction(session: Session) -> None:
    with suppress(Exception):
        if session.in_transaction():
            session.rollback()
