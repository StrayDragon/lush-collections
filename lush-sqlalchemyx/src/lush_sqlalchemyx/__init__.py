"""lush-sqlalchemyx — SQLAlchemy DAL 实现 + async/sync MySQL manager + 框架集成.

使用前须在应用启动时调用 :func:`setup_dal_hooks` 注册 Session 事件监听器:

- Flask: 使用 ``LushFlaskSQLAlchemy.init_db()`` 时自动调用
- FastAPI: 在 ``lifespan`` 中调用 ``setup_dal_hooks()``
- 其他场景: 在创建 Session 前调用一次 ``setup_dal_hooks()``

不调用则软删除、只读保护等钩子不会生效。
"""

from lush_sqlalchemyx.base.dal import (
    is_soft_delete_hooks_registered,
    register_soft_delete_hooks,
    setup_dal_hooks,
    unregister_soft_delete_hooks,
)

__all__ = (
    "is_soft_delete_hooks_registered",
    "register_soft_delete_hooks",
    "setup_dal_hooks",
    "unregister_soft_delete_hooks",
)
