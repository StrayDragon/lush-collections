from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager, suppress
from typing import Any, ClassVar, TypeVar, cast

import sqlalchemy as sa
from sqlalchemy import CursorResult, TextClause, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from lush_sqlalchemyx.base.dal import READONLY_SESSION_FLAG
from lush_sqlalchemyx.mgrs.mysql._pool_config import MySQLPoolConfig
from lush_sqlalchemyx.same_impl_just_warn_wrapper import AsyncSession as WarnWrappedAsyncSession

SessionT = TypeVar("SessionT", AsyncSession, WarnWrappedAsyncSession)


class AsyncMySQLManager:
    """异步 MySQL 数据库管理器."""

    _default_pool_config: ClassVar[type[MySQLPoolConfig]] = MySQLPoolConfig

    def __init__(
        self,
        database_url: str,
        pool_config: MySQLPoolConfig | None = None,
        **engine_kwargs: Any,
    ) -> None:
        base = pool_config or self._default_pool_config()
        final_kwargs = base.to_engine_kwargs()

        if "poolclass" in engine_kwargs:
            for key in ("pool_size", "max_overflow", "pool_recycle"):
                _ = final_kwargs.pop(key, None)

        final_kwargs.update(engine_kwargs)

        self.async_engine: AsyncEngine = create_async_engine(
            database_url,
            **final_kwargs,
        )

        self.async_session_local: Callable[..., AsyncSession] = async_sessionmaker(
            bind=self.async_engine,
            autoflush=False,
            expire_on_commit=False,
            autocommit=False,
        )

    @asynccontextmanager
    async def got_manual_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.async_session_local() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    @asynccontextmanager
    async def got_soft_impl_auto_commit_session(self) -> AsyncGenerator[WarnWrappedAsyncSession, None]:
        async with self.async_session_local() as session:
            try:
                yield cast("WarnWrappedAsyncSession", session)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    @asynccontextmanager
    async def got_readonly_session(self) -> AsyncGenerator[WarnWrappedAsyncSession, None]:
        async with self.async_session_local() as session:
            session.info[READONLY_SESSION_FLAG] = True
            try:
                with suppress(Exception):
                    _ = await session.execute(sa.text("SET TRANSACTION READ ONLY"))
                yield cast("WarnWrappedAsyncSession", session)
                await session.rollback()
            except Exception:
                await session.rollback()
                raise
            finally:
                try:
                    session.info.pop(READONLY_SESSION_FLAG, None)
                finally:
                    await session.close()

    async def health_check(self) -> bool:
        try:
            async with self.got_manual_session() as session:
                _ = await session.execute(sa.text("SELECT 1"))
                return True
        except Exception:
            return False

    async def close(self) -> None:
        if self.async_engine:
            await self.async_engine.dispose()

    async def execute_sql(
        self,
        sql_text: str | TextClause,
        params: dict[str, Any] | list[dict[str, Any]] | None = None,
        execution_options: dict[str, Any] | None = None,
    ) -> CursorResult[Any]:
        async with self.async_engine.connect() as conn:
            return await aexecute_sql(
                conn,
                sql_text,
                params,
                execution_options,
            )


async def aexecute_sql(
    conn: AsyncConnection,
    sql_text: str | TextClause,
    params: dict[str, Any] | list[dict[str, Any]] | None = None,
    execution_options: dict[str, Any] | None = None,
) -> CursorResult[Any]:
    if params is None:
        params = {}

    stmt = sql_text if isinstance(sql_text, TextClause) else text(sql_text)

    return await conn.execute(stmt, params, execution_options=execution_options)


@asynccontextmanager
async def async_configured_session_temporarily(
    session: SessionT,
    *,
    autoflush: bool | None = None,
    autocommit: bool | None = None,
) -> AsyncGenerator[SessionT, None]:
    original_autoflush = session.autoflush
    changed_autoflush = False

    try:
        if autoflush is not None and original_autoflush != autoflush:
            session.autoflush = autoflush
            changed_autoflush = True

        yield session

        if autocommit is True:
            await session.commit()

    except Exception:
        await session.rollback()
        raise
    finally:
        if changed_autoflush:
            session.autoflush = original_autoflush


async def async_must_rollback_if_in_transaction(session: AsyncSession | WarnWrappedAsyncSession) -> None:
    with suppress(Exception):
        if session.in_transaction():
            await session.rollback()
