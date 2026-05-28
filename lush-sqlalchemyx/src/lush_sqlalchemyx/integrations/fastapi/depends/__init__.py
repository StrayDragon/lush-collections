"""FastAPI 依赖工厂:为 AsyncMySQL 管理器与会话提供依赖注入工具.

使用本模块前, 请在 FastAPI lifespan 中调用 ``setup_dal_hooks()``::

    from contextlib import asynccontextmanager
    from lush_sqlalchemyx import setup_dal_hooks


    @asynccontextmanager
    async def lifespan(app):
        setup_dal_hooks()
        yield

不调用则软删除、只读保护等 Session 事件钩子不会生效.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import ClassVar, Generic

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from lush_sqlalchemyx.mgrs import AsyncMySQLManager, AsyncMySQLManagersMapper, DBEnumT
from lush_sqlalchemyx.same_impl_just_warn_wrapper import AsyncSession as WarnWrappedAsyncSession


class MySQLManagerMapperFastAPIDepends(Generic[DBEnumT]):
    """为 FastAPI 提供 AsyncMySQL 管理器相关依赖.

    该工具类将 `Request.state` 中预先注入的 `AsyncMySQLManagersMapper`
    暴露为可复用的依赖工厂,便于在路由或依赖模块中快速获取数据库管理器与会话.
    """

    state_name: ClassVar[str] = "mysql_mgrs_mapper"

    @classmethod
    async def get_async_mysql_managers_mapper(cls, request: Request) -> AsyncMySQLManagersMapper[DBEnumT]:
        """获取当前请求绑定的数据库管理器映射.

        Args:
            request (Request): FastAPI 请求对象,需要保证其 `state` 中存在管理器映射.

        Returns:
            AsyncMySQLManagersMapper[DBEnumT]: 预先注入到请求状态的数据库管理器映射.
        """
        return getattr(request.state, cls.state_name)

    @classmethod
    def get_async_mysql_manager_by_bind_depends_factory(
        cls,
        bind: DBEnumT,
    ) -> Callable[[Request], Awaitable[AsyncMySQLManager]]:
        """构造指定数据库枚举的管理器依赖.

        Args:
            bind (DBEnumT): 目标数据库枚举值.

        Returns:
            Callable[[Request], Awaitable[AsyncMySQLManager]]: FastAPI 依赖函数,用于获取对应的 `AsyncMySQLManager`.
        """

        async def _get_manager(request: Request) -> AsyncMySQLManager:
            return (await cls.get_async_mysql_managers_mapper(request)).get_manager(bind)

        return _get_manager

    @classmethod
    def get_async_db_manual_mysql_session(
        cls,
        bind: DBEnumT,
    ) -> Callable[[Request], AsyncIterator[AsyncSession]]:
        """构造手动提交的数据库会话依赖.

        Args:
            bind (DBEnumT): 目标数据库枚举值.

        Returns:
            Callable[[Request], AsyncIterator[AsyncSession]]: FastAPI 依赖函数,提供手动事务控制的 `AsyncSession`.

        Yields:
            AsyncSession: 需由使用方显式提交或回滚的数据库会话.
        """

        async def _get_session(request: Request) -> AsyncIterator[AsyncSession]:
            async with (await cls.get_async_mysql_manager_by_bind_depends_factory(bind)(request)).got_manual_session() as session:
                yield session

        return _get_session

    @classmethod
    def get_async_db_tx_session(
        cls,
        bind: DBEnumT,
    ) -> Callable[[Request], AsyncIterator[WarnWrappedAsyncSession]]:
        """构造自动提交的事务型会话依赖.

        Args:
            bind (DBEnumT): 目标数据库枚举值.

        Returns:
            Callable[[Request], AsyncIterator[WarnWrappedAsyncSession]]: FastAPI 依赖函数,提供自动提交的事务会话.

        Yields:
            WarnWrappedAsyncSession: 在生成器退出时自动提交的事务会话,异常时自动回滚.
        """

        async def _get_session(request: Request) -> AsyncIterator[WarnWrappedAsyncSession]:
            async with (
                await cls.get_async_mysql_manager_by_bind_depends_factory(bind)(request)
            ).got_soft_impl_auto_commit_session() as session:
                yield session

        return _get_session

    @classmethod
    def get_async_db_ro_session(
        cls,
        bind: DBEnumT,
    ) -> Callable[[Request], AsyncIterator[WarnWrappedAsyncSession]]:
        """构造只读会话依赖.

        Args:
            bind (DBEnumT): 目标数据库枚举值.

        Returns:
            Callable[[Request], AsyncIterator[WarnWrappedAsyncSession]]: FastAPI 依赖函数,提供只读事务会话.

        Yields:
            WarnWrappedAsyncSession: 标记为只读并在退出时回滚的事务会话.
        """

        async def _get_session(request: Request) -> AsyncIterator[WarnWrappedAsyncSession]:
            async with (await cls.get_async_mysql_manager_by_bind_depends_factory(bind)(request)).got_readonly_session() as session:
                yield session

        return _get_session
