"""分层 ABC 抽象接口.

按能力分组的 ORM 无关 DAL 抽象基类, 每个层级有 Async / Sync 两个版本.
下游 ORM 适配包通过继承这些 ABC 并绑定泛型参数来实现具体 DAL.

仅包含最通用的 Read + Write 操作.
Lock / AdvancedWrite / BatchField / RawSQL 等 ORM 特有操作由具体实现包提供.
"""

from ._types import NO_ENTITY, NO_SESSION, NoEntity, NoSession
from .base_composed import BaseAsyncBaseDAL, BaseSyncBaseDAL
from .base_read import BaseAsyncReadDAL, BaseSyncReadDAL
from .base_write import BaseAsyncWriteDAL, BaseSyncWriteDAL
from .composed import AbstractAsyncBaseDAL, AbstractSyncBaseDAL
from .read import AbstractAsyncReadDAL, AbstractSyncReadDAL
from .sessionless import (
    AbstractAsyncSessionlessBaseDAL,
    AbstractAsyncSessionlessReadDAL,
    AbstractAsyncSessionlessWriteDAL,
    AbstractSyncSessionlessBaseDAL,
    AbstractSyncSessionlessReadDAL,
    AbstractSyncSessionlessWriteDAL,
)
from .write import AbstractAsyncWriteDAL, AbstractSyncWriteDAL

__all__ = [
    "NO_ENTITY",
    "NO_SESSION",
    "AbstractAsyncBaseDAL",
    "AbstractAsyncReadDAL",
    "AbstractAsyncSessionlessBaseDAL",
    "AbstractAsyncSessionlessReadDAL",
    "AbstractAsyncSessionlessWriteDAL",
    "AbstractAsyncWriteDAL",
    "AbstractSyncBaseDAL",
    "AbstractSyncReadDAL",
    "AbstractSyncSessionlessBaseDAL",
    "AbstractSyncSessionlessReadDAL",
    "AbstractSyncSessionlessWriteDAL",
    "AbstractSyncWriteDAL",
    "BaseAsyncBaseDAL",
    "BaseAsyncReadDAL",
    "BaseAsyncWriteDAL",
    "BaseSyncBaseDAL",
    "BaseSyncReadDAL",
    "BaseSyncWriteDAL",
    "NoEntity",
    "NoSession",
]
