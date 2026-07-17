"""``lush_sqlalchemyx.base.dal`` 公共导出层.

所有原先可从此模块导入的符号保持不变, 同时新增同步模式相关符号.
"""

# --- shared (sync/async agnostic) ---
# --- lush-dal-protocol ABCs (ORM 无关的抽象层) ---
from lush_dal_protocol import (
    AbstractAsyncBaseDAL,
    AbstractAsyncReadDAL,
    AbstractAsyncWriteDAL,
    AbstractSyncBaseDAL,
    AbstractSyncReadDAL,
    AbstractSyncWriteDAL,
)
from lush_dal_protocol.params.pagination import CursorPagination, CursorResult, OffsetPagination, PageResult

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
    async_temp_set_lock_wait_timeout,
    async_with_retry,
)
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
    FieldIsDeleteSoftDeleteTableMixin,
    FieldMixin,
    ReadOnlyMixin,
    RetryConfig,
    SoftDeleteTableMixin,
    SQLATableT,
    escape_like,
    filtered_in_sql_values,
    is_soft_delete_hooks_registered,
    register_soft_delete_hooks,
    setup_dal_hooks,
    unregister_soft_delete_hooks,
)

# --- dynamic (no ORM table class) ---
from ._dynamic import (
    DynamicAsyncDAL,
    DynamicSyncDAL,
    DynamicTableConfig,
    PrimaryKeyT,
    TableRef,
    derive_columns_from_dto,
    derive_pk_from_dto,
)
from ._pagination import (
    build_cursor_stmt,
    build_offset_stmt,
    make_cursor_result,
    make_page_result,
)

# --- sync ---
from ._sync import (
    BasicSyncBaseTable,
    ReadOnlySyncBaseDAL,
    ReadOnlySyncBaseTable,
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
    "FieldIsDeleteSoftDeleteTableMixin",
    "escape_like",
    "filtered_in_sql_values",
    "is_soft_delete_hooks_registered",
    "register_soft_delete_hooks",
    "setup_dal_hooks",
    "unregister_soft_delete_hooks",
    # dynamic
    "DynamicAsyncDAL",
    "DynamicSyncDAL",
    "DynamicTableConfig",
    "PrimaryKeyT",
    "TableRef",
    "derive_columns_from_dto",
    "derive_pk_from_dto",
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
    "async_temp_set_lock_wait_timeout",
    "async_with_retry",
    # sync
    "BasicSyncBaseTable",
    "ReadOnlySyncBaseDAL",
    "ReadOnlySyncBaseTable",
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
    # pagination
    "CursorPagination",
    "CursorResult",
    "OffsetPagination",
    "PageResult",
    "build_cursor_stmt",
    "build_offset_stmt",
    "make_cursor_result",
    "make_page_result",
    # lush-dal-protocol ABCs
    "AbstractAsyncBaseDAL",
    "AbstractAsyncReadDAL",
    "AbstractAsyncWriteDAL",
    "AbstractSyncBaseDAL",
    "AbstractSyncReadDAL",
    "AbstractSyncWriteDAL",
)
