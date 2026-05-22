"""原始 SQL 操作 ABC 层."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic

from lush_dal_protocol.abc._types import SessionT
from lush_dal_protocol.params.extra import ExtraT


class AbstractSyncRawSQLDAL(ABC, Generic[SessionT, ExtraT]):
    """同步原始 SQL 操作 DAL 抽象基类."""

    @classmethod
    @abstractmethod
    def execute_sql(cls, session: SessionT, sql: str | Any, params: Any | None = None, extra: ExtraT | None = None) -> Any:
        """执行原始 SQL (读写皆可)."""
        ...

    @classmethod
    @abstractmethod
    def execute_readonly_sql(cls, session: SessionT, sql: str | Any, params: Any | None = None, extra: ExtraT | None = None) -> Any:
        """执行只读原始 SQL."""
        ...


class AbstractAsyncRawSQLDAL(ABC, Generic[SessionT, ExtraT]):
    """异步原始 SQL 操作 DAL 抽象基类.

    语义与 ``AbstractSyncRawSQLDAL`` 一致, 所有方法为 ``async def``.
    """

    @classmethod
    @abstractmethod
    async def execute_sql(cls, session: SessionT, sql: str | Any, params: Any | None = None, extra: ExtraT | None = None) -> Any:
        """执行原始 SQL (读写皆可)."""
        ...

    @classmethod
    @abstractmethod
    async def execute_readonly_sql(cls, session: SessionT, sql: str | Any, params: Any | None = None, extra: ExtraT | None = None) -> Any:
        """执行只读原始 SQL."""
        ...
