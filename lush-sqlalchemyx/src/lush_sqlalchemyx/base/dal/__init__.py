"""``lush_sqlalchemyx.base.dal`` 公共导出层.

所有原先可从此模块导入的符号保持不变, 同时新增同步模式相关符号.
"""

# --- shared (sync/async agnostic) ---
from ._common import (
    DEFAULT_RETRY_CONFIG,
    OPTIMISTIC_LOCK_ERROR_MSG_TRAIT,
    PESSIMISTIC_LOCK_ERROR_MSG_TRAIT,
    READONLY_SESSION_FLAG,
    BaseCU,
    BaseDTO,
    BaseModelT,
    CUModelT,
    DBRetryableError,
    DTOModelT,
    FieldMixin,
    ReadOnlyMixin,
    RetryConfig,
    SQLATableT,
    SoftDeleteTableMixin,
    StdBaseCU,
    StdBaseDTO,
    T,
    V,
    _ensure_strict_fields,
    escape_like,
    filtered_in_sql_values,
)

# Event listener references — accessed by tests via getattr(module, name).
from ._common import __prevent_readonly_write as __prevent_readonly_write  # noqa: F401, PLC2701
from ._common import __receive_before_flush as __receive_before_flush  # noqa: F401, PLC2701

# --- async (requires sqlalchemy[asyncio]) ---
from ._async import (
    AsyncBaseDAL,
    AsyncRawDAL,
    AsyncRawReadDAL,
    AsyncReadDAL,
    AsyncSQLATableT,
    AsyncSqlATableBase,
    AsyncWriteDAL,
    AsyncXDALOp,
    BasicAsyncBaseTable,
    ReadOnlyAsyncBaseDAL,
    ReadOnlyBasicAsyncBaseTable,
    StdAsyncBaseTable,
    StdReadOnlyBasicAsyncBaseTable,
    async_temp_set_lock_wait_timeout,
    async_with_retry,
)

# --- lush-dalx protocols (ORM 无关的抽象层) ---
from lush_dalx import (
    AsyncBaseDALProtocol,
    AsyncReadDALProtocol,
    AsyncWriteDALProtocol,
    SyncBaseDALProtocol,
    SyncReadDALProtocol,
    SyncWriteDALProtocol,
)

# --- sync ---
from ._sync import (
    BasicSyncBaseTable,
    ReadOnlySyncBaseDAL,
    ReadOnlySyncBaseTable,
    StdReadOnlySyncBaseTable,
    StdSyncBaseTable,
    SyncBaseDAL,
    SyncRawDAL,
    SyncRawReadDAL,
    SyncReadDAL,
    SyncSQLATableT,
    SyncSqlATableBase,
    SyncWriteDAL,
    SyncXDALOp,
    sync_temp_set_lock_wait_timeout,
    sync_with_retry,
)

__all__ = (
    # common
    "DEFAULT_RETRY_CONFIG",
    "OPTIMISTIC_LOCK_ERROR_MSG_TRAIT",
    "PESSIMISTIC_LOCK_ERROR_MSG_TRAIT",
    "READONLY_SESSION_FLAG",
    "BaseCU",
    "BaseDTO",
    "BaseModelT",
    "CUModelT",
    "DBRetryableError",
    "DTOModelT",
    "FieldMixin",
    "ReadOnlyMixin",
    "RetryConfig",
    "SQLATableT",
    "SoftDeleteTableMixin",
    "StdBaseCU",
    "StdBaseDTO",
    "T",
    "V",
    "_ensure_strict_fields",
    "escape_like",
    "filtered_in_sql_values",
    # async
    "AsyncBaseDAL",
    "AsyncRawDAL",
    "AsyncRawReadDAL",
    "AsyncReadDAL",
    "AsyncSQLATableT",
    "AsyncSqlATableBase",
    "AsyncWriteDAL",
    "AsyncXDALOp",
    "BasicAsyncBaseTable",
    "ReadOnlyAsyncBaseDAL",
    "ReadOnlyBasicAsyncBaseTable",
    "StdAsyncBaseTable",
    "StdReadOnlyBasicAsyncBaseTable",
    "async_temp_set_lock_wait_timeout",
    "async_with_retry",
    # sync
    "BasicSyncBaseTable",
    "ReadOnlySyncBaseDAL",
    "ReadOnlySyncBaseTable",
    "StdReadOnlySyncBaseTable",
    "StdSyncBaseTable",
    "SyncBaseDAL",
    "SyncRawDAL",
    "SyncRawReadDAL",
    "SyncReadDAL",
    "SyncSQLATableT",
    "SyncSqlATableBase",
    "SyncWriteDAL",
    "SyncXDALOp",
    "sync_temp_set_lock_wait_timeout",
    "sync_with_retry",
    # lush-dalx protocols
    "AsyncBaseDALProtocol",
    "AsyncReadDALProtocol",
    "AsyncWriteDALProtocol",
    "SyncBaseDALProtocol",
    "SyncReadDALProtocol",
    "SyncWriteDALProtocol",
)
