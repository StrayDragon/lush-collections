"""分层 ABC 抽象接口.

按能力分组的 ORM 无关 DAL 抽象基类, 每个层级有 Async / Sync 两个版本.
下游 ORM 适配包通过继承这些 ABC 并绑定泛型参数来实现具体 DAL.
"""

from .advanced_write import AbstractAsyncAdvancedWriteDAL, AbstractSyncAdvancedWriteDAL
from .batch_field import AbstractAsyncBatchFieldDAL, AbstractSyncBatchFieldDAL
from .composed import AbstractAsyncBaseDAL, AbstractSyncBaseDAL
from .lock import AbstractAsyncLockDAL, AbstractSyncLockDAL
from .raw_sql import AbstractAsyncRawSQLDAL, AbstractSyncRawSQLDAL
from .read import AbstractAsyncReadDAL, AbstractSyncReadDAL
from .write import AbstractAsyncWriteDAL, AbstractSyncWriteDAL

__all__ = [
    "AbstractAsyncAdvancedWriteDAL",
    "AbstractAsyncBaseDAL",
    "AbstractAsyncBatchFieldDAL",
    "AbstractAsyncLockDAL",
    "AbstractAsyncRawSQLDAL",
    "AbstractAsyncReadDAL",
    "AbstractAsyncWriteDAL",
    "AbstractSyncAdvancedWriteDAL",
    "AbstractSyncBaseDAL",
    "AbstractSyncBatchFieldDAL",
    "AbstractSyncLockDAL",
    "AbstractSyncRawSQLDAL",
    "AbstractSyncReadDAL",
    "AbstractSyncWriteDAL",
]
