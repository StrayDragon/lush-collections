"""``lush_sqlalchemyx.base.dal`` 公共导出层.

所有原先可从此模块导入的符号保持不变, 同时新增同步模式相关符号.
"""

# --- shared (sync/async agnostic) ---
# --- lush-dal-protocol ABCs (ORM 无关的抽象层) ---
from lush_dal_protocol import (
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

# --- async (requires sqlalchemy[asyncio]) ---
from ._async import (
    AsyncBaseDAL,
    AsyncRawDAL,
    AsyncRawReadDAL,
    AsyncReadDAL,
    AsyncSqlATableBase,
    AsyncSQLATableT,
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

# --- V2 (ABC-compliant, options-based) ---
from ._async_v2 import AsyncBaseDALV2, AsyncReadDALV2, AsyncWriteDALV2
from ._common import (
    DEFAULT_RETRY_CONFIG,
    OPTIMISTIC_LOCK_ERROR_MSG_TRAIT,
    PESSIMISTIC_LOCK_ERROR_MSG_TRAIT,
    READONLY_SESSION_FLAG,
    BaseCU,
    BaseDTO,
    CUModelT,
    DBRetryableError,
    DTOModelT,
    FieldMixin,
    ReadOnlyMixin,
    RetryConfig,
    SoftDeleteTableMixin,
    SQLATableT,
    StdBaseCU,
    StdBaseDTO,
    escape_like,
    filtered_in_sql_values,
)

# Event listener references — accessed by tests via getattr(module, name).
from ._common import __prevent_readonly_write as __prevent_readonly_write  # pyright: ignore[reportPrivateUsage]
from ._common import __receive_before_flush as __receive_before_flush  # pyright: ignore[reportPrivateUsage]
from ._params import SQLAExtra

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
    SyncSqlATableBase,
    SyncSQLATableT,
    SyncWriteDAL,
    SyncXDALOp,
    sync_temp_set_lock_wait_timeout,
    sync_with_retry,
)
from ._sync_v2 import SyncBaseDALV2, SyncReadDALV2, SyncWriteDALV2

__all__ = (
    # common
    "DEFAULT_RETRY_CONFIG",
    "OPTIMISTIC_LOCK_ERROR_MSG_TRAIT",
    "PESSIMISTIC_LOCK_ERROR_MSG_TRAIT",
    "READONLY_SESSION_FLAG",
    "BaseCU",
    "BaseDTO",
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
    # V2
    "AsyncBaseDALV2",
    "AsyncReadDALV2",
    "AsyncWriteDALV2",
    "SQLAExtra",
    "SyncBaseDALV2",
    "SyncReadDALV2",
    "SyncWriteDALV2",
    # lush-dal-protocol ABCs
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
)
