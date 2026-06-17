"""ABC 层共享的泛型参数定义."""

from __future__ import annotations

from typing_extensions import TypeVar as TypeVarExt


class NoSession:
    """万能占位类型 — 表示此 DAL 不绑定任何 session / connection.

    用法::

        # 不关心 session 类型 (session 为可选 keyword arg)
        class MyDAL(DtoSyncReadDAL[MyDTO, int]): ...


        # 绑定 SQLAlchemy Session
        class MyDAL(DtoSyncReadDAL[Session, MyDTO, int]): ...


        # 绑定其他 ORM 连接类型
        class MyDAL(DtoSyncReadDAL[TortoiseConnection, MyDTO, int]): ...
    """


class NoEntity:
    """万能占位类型 — 表示此 DAL 不绑定任何 ORM 实体类.

    用于 ``EntityT`` 的默认值, 允许 ``Dto*`` 协议跳过实体类型绑定.
    """


NO_SESSION = NoSession()  # 单例哨兵值, 用作 session 参数默认值.
NO_ENTITY = NoEntity()  # 单例哨兵值.

SessionT = TypeVarExt("SessionT", default=NoSession)
EntityT = TypeVarExt("EntityT", default=NoEntity)
PrimaryKeyT = TypeVarExt("PrimaryKeyT", default=int)
