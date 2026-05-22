"""lush-dal-protocol — ORM 无关的数据访问层抽象接口.

本包提供分层 ABC 抽象基类和共享类型, 不依赖任何具体 ORM.
下游适配包 (如 lush-sqlalchemyx) 继承 ABC 并绑定泛型参数来实现具体 DAL.
"""

from .abc import (
    AbstractAsyncAdvancedWriteDAL,
    AbstractAsyncBaseDAL,
    AbstractAsyncBatchFieldDAL,
    AbstractAsyncLockDAL,
    AbstractAsyncRawSQLDAL,
    AbstractAsyncReadDAL,
    AbstractAsyncWriteDAL,
    AbstractSyncAdvancedWriteDAL,
    AbstractSyncBaseDAL,
    AbstractSyncBatchFieldDAL,
    AbstractSyncLockDAL,
    AbstractSyncRawSQLDAL,
    AbstractSyncReadDAL,
    AbstractSyncWriteDAL,
)
from .dto import BaseCU, BaseDTO, CUModelT, DTOModelT, StdBaseCU, StdBaseDTO
from .errors import DBRetryableError
from .params import LockOptions, OptimisticLockOptions, PartialUpdateOptions, UpdateOptions
from .testing import (
    AsyncBaseDALConformanceTests,
    AsyncReadDALConformanceTests,
    AsyncWriteDALConformanceTests,
    SyncBaseDALConformanceTests,
    SyncReadDALConformanceTests,
    SyncWriteDALConformanceTests,
)
from .utils import DEFAULT_RETRY_CONFIG, RetryConfig, escape_like, filtered_in_sql_values

__all__ = [
    "DEFAULT_RETRY_CONFIG",
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
    "AsyncBaseDALConformanceTests",
    "AsyncReadDALConformanceTests",
    "AsyncWriteDALConformanceTests",
    "BaseCU",
    "BaseDTO",
    "CUModelT",
    "DBRetryableError",
    "DTOModelT",
    "LockOptions",
    "OptimisticLockOptions",
    "PartialUpdateOptions",
    "RetryConfig",
    "StdBaseCU",
    "StdBaseDTO",
    "SyncBaseDALConformanceTests",
    "SyncReadDALConformanceTests",
    "SyncWriteDALConformanceTests",
    "UpdateOptions",
    "escape_like",
    "filtered_in_sql_values",
]
