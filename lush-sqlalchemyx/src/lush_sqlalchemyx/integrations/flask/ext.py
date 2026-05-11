"""Flask-SQLAlchemy 桥接模块.

将 ``flask_sqlalchemy.SQLAlchemy`` 实例（或其底层 ``Engine``）包装为
``SyncMySQLManager``, 使 *lush-sqlalchemyx* 栈（DAL、Mapper 等）可以在
Flask 应用中透明运行, 同时保留 Flask-SQLAlchemy 的会话作用域管理.

本模块为 **可选模块** — 未安装 ``flask-sqlalchemy`` 时导入会抛出清晰的 ``ImportError``.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from enum import Enum
from typing import Any, ClassVar, Generic, TypeVar

try:
    from flask import g
    from flask_sqlalchemy import SQLAlchemy
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "Flask integration requires 'flask-sqlalchemy'. "
        "Install with: pip install 'lush-sqlalchemyx[flask]'"
    ) from _exc

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from lush_sqlalchemyx.mgrs.mysql.sync_manager import SyncMySQLManager
from lush_sqlalchemyx.mgrs.mysql.sync_mapper import SyncMySQLManagersMapper

FlaskDBEnumT = TypeVar("FlaskDBEnumT", bound=Enum)


class LushFlaskSQLAlchemy:
    """将 Flask-SQLAlchemy 的 ``db`` 桥接为 ``SyncMySQLManager``.

    支持两种初始化方式:

    1. **直接传入**::

        db = SQLAlchemy()
        lush = LushFlaskSQLAlchemy(db)

    2. **延迟初始化** (Flask factory pattern)::

        lush = LushFlaskSQLAlchemy()
        # ... later, in create_app()
        lush.init_db(db)
    """

    def __init__(self, db: SQLAlchemy | None = None) -> None:
        self._manager: SyncMySQLManager | None = None
        self._db: SQLAlchemy | None = None
        if db is not None:
            self.init_db(db)

    def init_db(self, db: SQLAlchemy) -> None:
        """绑定到 Flask-SQLAlchemy 实例."""
        self._db = db
        self._manager = SyncMySQLManager.from_engine(db.engine)

    @property
    def manager(self) -> SyncMySQLManager:
        if self._manager is None:
            raise RuntimeError("LushFlaskSQLAlchemy not initialized — call init_db(db) first")
        return self._manager

    def get_manager(self) -> SyncMySQLManager:
        return self.manager


class MySQLManagerMapperFlaskDepends(Generic[FlaskDBEnumT]):
    """为 Flask 提供 SyncMySQL 管理器相关依赖.

    与 FastAPI 版本 ``MySQLManagerMapperFastAPIDepends`` 对称,
    将 ``flask.g`` 中预先注入的 ``SyncMySQLManagersMapper``
    暴露为可复用的工具方法.
    """

    g_attr_name: ClassVar[str] = "mysql_mgrs_mapper"

    @classmethod
    def get_mapper(cls) -> SyncMySQLManagersMapper[FlaskDBEnumT]:
        mapper = getattr(g, cls.g_attr_name, None)
        if mapper is None:
            raise RuntimeError(
                f"SyncMySQLManagersMapper not found on flask.g.{cls.g_attr_name}. "
                "Ensure it is set in a before_request hook."
            )
        return mapper

    @classmethod
    def get_manager_by_bind(cls, bind: FlaskDBEnumT) -> SyncMySQLManager:
        return cls.get_mapper().get_manager(bind)

    @classmethod
    @contextmanager
    def get_manual_session(cls, bind: FlaskDBEnumT) -> Generator[Session, None, None]:
        with cls.get_manager_by_bind(bind).got_manual_session() as session:
            yield session

    @classmethod
    @contextmanager
    def get_tx_session(cls, bind: FlaskDBEnumT) -> Generator[Session, None, None]:
        with cls.get_manager_by_bind(bind).got_soft_impl_auto_commit_session() as session:
            yield session

    @classmethod
    @contextmanager
    def get_ro_session(cls, bind: FlaskDBEnumT) -> Generator[Session, None, None]:
        with cls.get_manager_by_bind(bind).got_readonly_session() as session:
            yield session
