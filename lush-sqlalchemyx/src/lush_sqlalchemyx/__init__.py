"""lush-sqlalchemyx — SQLAlchemy DAL 实现 + async/sync MySQL manager + 框架集成.

导入本包时会自动注册软删除 Session 事件监听器.
如需显式管理钩子生命周期, 参见 :func:`register_soft_delete_hooks` 等.
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
