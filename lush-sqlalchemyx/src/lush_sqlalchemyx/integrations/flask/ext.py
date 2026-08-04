"""Flask-SQLAlchemy 桥接模块.

提供两条集成路径:

**路径 1 — 独立 Engine** (``LushFlaskSQLAlchemy`` / ``MySQLManagerMapperFlaskDepends``):
将 Flask-SQLAlchemy 的 ``Engine`` 包装为 ``SyncMySQLManager``, 由 lush 自行管理 session 生命周期.
适用于新建项目或完全迁移到 lush DAL 的场景.

**路径 2 — 复用 db.session** (``FlaskSessionDALAdapter``):
直接复用 Flask-SQLAlchemy 已有的 ``db.session`` (request-scoped), 以适配器模式
将 lush 的 classmethod DAL 包装为实例方法. 适用于已有 Flask 项目渐进集成.
事务管理仍由 Flask-SQLAlchemy 的 ``auto_commit``/``db.session`` 控制.

本模块为 **可选模块** — 未安装 ``flask-sqlalchemy`` 时导入会抛出清晰的 ``ImportError``.
"""

from __future__ import annotations

from collections.abc import Generator, Iterable, Iterator
from contextlib import contextmanager
from enum import Enum
from typing import Any, ClassVar, Generic, TypeVar

try:
    from flask import g
    from flask_sqlalchemy import SQLAlchemy
except ImportError as _exc:  # pragma: no cover
    raise ImportError("Flask integration requires 'flask-sqlalchemy'. Install with: pip install 'lush-sqlalchemyx[flask]'") from _exc

from sqlalchemy.orm import Session

from lush_sqlalchemyx import setup_dal_hooks
from lush_sqlalchemyx.base.dal._common import CUModelT, DTOModelT, NonePolicy, SQLATableT
from lush_sqlalchemyx.base.dal._sync import SyncBaseDAL, SyncReadDAL, SyncWriteDAL
from lush_sqlalchemyx.mgrs.mysql.sync_manager import SyncMySQLManager
from lush_sqlalchemyx.mgrs.mysql.sync_mapper import SyncMySQLManagersMapper

FlaskDBEnumT = TypeVar("FlaskDBEnumT", bound=Enum)


# ---------------------------------------------------------------------------
# 路径 1: 独立 Engine 管理
# ---------------------------------------------------------------------------


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
        """绑定到 Flask-SQLAlchemy 实例, 并注册 DAL Session 事件钩子."""
        self._db = db
        self._manager = SyncMySQLManager.from_engine(db.engine)
        setup_dal_hooks()

    @property
    def manager(self) -> SyncMySQLManager:
        """获取 SyncMySQLManager 实例, 未初始化时抛出 RuntimeError."""
        if self._manager is None:
            raise RuntimeError("LushFlaskSQLAlchemy not initialized — call init_db(db) first")
        return self._manager

    def get_manager(self) -> SyncMySQLManager:
        """获取 SyncMySQLManager 实例 (manager 属性的方法版)."""
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
        """从 flask.g 获取预注入的 mapper."""
        mapper = getattr(g, cls.g_attr_name, None)
        if mapper is None:
            raise RuntimeError(
                f"SyncMySQLManagersMapper not found on flask.g.{cls.g_attr_name}. Ensure it is set in a before_request hook."
            )
        return mapper

    @classmethod
    def get_manager_by_bind(cls, bind: FlaskDBEnumT) -> SyncMySQLManager:
        """根据 bind 枚举获取对应的管理器."""
        return cls.get_mapper().get_manager(bind)

    @classmethod
    @contextmanager
    def get_manual_session(cls, bind: FlaskDBEnumT) -> Generator[Session, None, None]:
        """获取手动管理的 session (不自动 commit)."""
        with cls.get_manager_by_bind(bind).got_manual_session() as session:
            yield session

    @classmethod
    @contextmanager
    def get_tx_session(cls, bind: FlaskDBEnumT) -> Generator[Session, None, None]:
        """获取自动提交的事务 session."""
        with cls.get_manager_by_bind(bind).got_soft_impl_auto_commit_session() as session:
            yield session

    @classmethod
    @contextmanager
    def get_ro_session(cls, bind: FlaskDBEnumT) -> Generator[Session, None, None]:
        """获取只读 session."""
        with cls.get_manager_by_bind(bind).got_readonly_session() as session:
            yield session


# ---------------------------------------------------------------------------
# 路径 2: 复用 Flask-SQLAlchemy 的 db.session
# ---------------------------------------------------------------------------


class FlaskSessionDALAdapter(Generic[SQLATableT, DTOModelT, CUModelT]):
    """Flask-SQLAlchemy session 适配器 — 将 lush classmethod DAL 桥接为实例方法.

    适用于已有 Flask 项目中, 希望复用 Flask-SQLAlchemy 的 ``db.session``
    (request-scoped) 而非创建独立 Engine 的场景.

    使用方式::

        # 1. 定义 DAL (继承 lush 的 SyncWriteDAL)
        class UserDAL(SyncWriteDAL[UserTable, UserDTO, UserCU]):
            _Table = UserTable
            _DTO = UserDTO


        # 2. 创建适配器
        class UserFlaskDAL(FlaskSessionDALAdapter[UserTable, UserDTO, UserCU]):
            _dal_class = UserDAL


        # 3. 在服务启动时绑定 db
        FlaskSessionDALAdapter.bind_db(db)

        # 4. 在 BLL 中使用 (自动使用 db.session)
        user_dal = UserFlaskDAL()
        entity = user_dal.create(UserCU(name="test"))  # 自动用 db.session
        user = user_dal.get_by_id(1)

        # 5. 事务管理仍用 Flask 的方式
        with db.auto_commit():
            user_dal.create(UserCU(name="a"))
            user_dal.create(UserCU(name="b"))
    """

    _dal_class: ClassVar[type[SyncBaseDAL[Any, Any, Any] | SyncWriteDAL[Any, Any, Any] | SyncReadDAL[Any, Any]]]
    _db: ClassVar[SQLAlchemy | None] = None

    @classmethod
    def bind_db(cls, db: SQLAlchemy) -> None:
        """绑定 Flask-SQLAlchemy 实例 (应在应用启动时调用一次).

        所有子类共享同一个 ``db`` 引用.
        """
        FlaskSessionDALAdapter._db = db

    @property
    def session(self) -> Session:
        """获取当前 Flask request 作用域的 session."""
        if self._db is None:
            raise RuntimeError("FlaskSessionDALAdapter not bound to db. Call FlaskSessionDALAdapter.bind_db(db) during app init.")
        return self._db.session  # pyright: ignore[reportReturnType]

    def get_by_id(self, entity_id: int) -> SQLATableT | None:
        """根据主键 ID 获取实体."""
        return self._dal_class.get_by_id(self.session, entity_id)

    def get_all(self, skip: int = 0, limit: int = 100) -> list[DTOModelT]:
        """分页获取实体列表 (DTO)."""
        return self._dal_class.get_all(self.session, skip=skip, limit=limit)

    def count(self) -> int:
        """统计实体总数."""
        return self._dal_class.count(self.session)

    def exists(self, entity_id: int) -> bool:
        """判断实体是否存在."""
        return self._dal_class.exists(self.session, entity_id)

    def ret_dto_after_get_by_id(self, entity_id: int, need_refresh: bool = True) -> DTOModelT | None:
        """获取实体并转为 DTO."""
        return self._dal_class.ret_dto_after_get_by_id(self.session, entity_id, need_refresh=need_refresh)

    def batch_get_id__entity(self, entity_ids: Iterable[int]) -> dict[int, SQLATableT]:
        """批量获取 {id: entity} 字典."""
        return self._dal_class.batch_get_id__entity(self.session, entity_ids)

    def batch_get_id__dto(self, entity_ids: Iterable[int]) -> dict[int, DTOModelT]:
        """批量获取 {id: DTO} 字典."""
        return self._dal_class.batch_get_id__dto(self.session, entity_ids)

    def create(self, cu: CUModelT, need_refresh: bool = True) -> SQLATableT:
        """创建实体 (flush 但不 commit, 事务由调用方控制)."""
        return self._dal_class.create(self.session, cu, need_refresh=need_refresh)

    def ret_dto_after_create(self, cu: CUModelT, need_refresh: bool = True) -> DTOModelT:
        """创建实体并返回 DTO."""
        return self._dal_class.ret_dto_after_create(self.session, cu, need_refresh=need_refresh)

    def update_only_set_by_id(
        self,
        entity_id: int,
        cu: CUModelT,
        need_refresh: bool = False,
        *,
        none_policy: NonePolicy = "ignore",
    ) -> SQLATableT | None:
        """仅更新 CU 中已设置的字段.

        ``none_policy`` 语义见 ``lush_sqlalchemyx.base.dal.NonePolicy``.
        """
        return self._dal_class.update_only_set_by_id(self.session, entity_id, cu, need_refresh=need_refresh, none_policy=none_policy)

    def delete_by_id(self, entity_id: int) -> bool:
        """根据 ID 删除实体."""
        return self._dal_class.delete_by_id(self.session, entity_id)

    def iter_record_dtos(self, *, batch_size: int = 500) -> Iterator[DTOModelT]:
        """以迭代器方式返回全部记录的 DTO."""
        return self._dal_class.iter_record_dtos(self.session, batch_size=batch_size)
