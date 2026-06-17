"""lush-dal-protocol — ORM 无关的数据访问层抽象接口.

本包提供分层 ABC 抽象基类和共享类型, 不依赖任何具体 ORM.
下游适配包 (如 lush-sqlalchemyx) 继承 ABC 并绑定泛型参数来实现具体 DAL.
"""

from .abc import (
    AbstractAsyncBaseDAL,
    AbstractAsyncReadDAL,
    AbstractAsyncSessionlessBaseDAL,
    AbstractAsyncSessionlessReadDAL,
    AbstractAsyncSessionlessWriteDAL,
    AbstractAsyncWriteDAL,
    AbstractSyncBaseDAL,
    AbstractSyncReadDAL,
    AbstractSyncSessionlessBaseDAL,
    AbstractSyncSessionlessReadDAL,
    AbstractSyncSessionlessWriteDAL,
    AbstractSyncWriteDAL,
    DtoAsyncDAL,
    DtoAsyncReadDAL,
    DtoAsyncWriteDAL,
    DtoSyncDAL,
    DtoSyncReadDAL,
    DtoSyncWriteDAL,
)
from .abc._types import NO_ENTITY, NO_SESSION, NoEntity, NoSession, PrimaryKeyT
from .dto import BaseCU, BaseDTO, CUModelT, DTOModelT, StdBaseCU, StdBaseDTO
from .errors import DBRetryableError
from .params import CursorPagination, CursorResult, OffsetPagination, PageResult
from .repository import AbstractAsyncRepository, AbstractSyncRepository
from .utils import DEFAULT_RETRY_CONFIG, RetryConfig, escape_like, filtered_in_sql_values

__all__ = [
    "DEFAULT_RETRY_CONFIG",
    "NO_ENTITY",
    "NO_SESSION",
    "AbstractAsyncBaseDAL",
    "AbstractAsyncReadDAL",
    "AbstractAsyncRepository",
    "AbstractAsyncSessionlessBaseDAL",
    "AbstractAsyncSessionlessReadDAL",
    "AbstractAsyncSessionlessWriteDAL",
    "AbstractAsyncWriteDAL",
    "AbstractSyncBaseDAL",
    "AbstractSyncReadDAL",
    "AbstractSyncRepository",
    "AbstractSyncSessionlessBaseDAL",
    "AbstractSyncSessionlessReadDAL",
    "AbstractSyncSessionlessWriteDAL",
    "AbstractSyncWriteDAL",
    "BaseCU",
    "BaseDTO",
    "CUModelT",
    "CursorPagination",
    "CursorResult",
    "DBRetryableError",
    "DTOModelT",
    "DtoAsyncDAL",
    "DtoAsyncReadDAL",
    "DtoAsyncWriteDAL",
    "DtoSyncDAL",
    "DtoSyncReadDAL",
    "DtoSyncWriteDAL",
    "NoEntity",
    "NoSession",
    "OffsetPagination",
    "PageResult",
    "PrimaryKeyT",
    "RetryConfig",
    "StdBaseCU",
    "StdBaseDTO",
    "escape_like",
    "filtered_in_sql_values",
]
