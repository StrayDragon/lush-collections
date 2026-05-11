"""lush-dalx — ORM 无关的数据访问层协议抽象.

本包仅包含纯 Protocol / 接口声明, 不依赖任何具体 ORM.
下游适配包 (如 lush-sqlalchemyx) 负责实现这些协议.
"""

from .dto import BaseCU, BaseDTO, CUModelT, DTOModelT, StdBaseCU, StdBaseDTO
from .errors import DBRetryableError
from .protocols import (
    AsyncBaseDALProtocol,
    AsyncReadDALProtocol,
    AsyncWriteDALProtocol,
    SyncBaseDALProtocol,
    SyncReadDALProtocol,
    SyncWriteDALProtocol,
)
from .retry import DEFAULT_RETRY_CONFIG, RetryConfig
from .utils import escape_like, filtered_in_sql_values

__all__ = [
    "AsyncBaseDALProtocol",
    "AsyncReadDALProtocol",
    "AsyncWriteDALProtocol",
    "BaseCU",
    "BaseDTO",
    "CUModelT",
    "DBRetryableError",
    "DEFAULT_RETRY_CONFIG",
    "DTOModelT",
    "RetryConfig",
    "StdBaseCU",
    "StdBaseDTO",
    "SyncBaseDALProtocol",
    "SyncReadDALProtocol",
    "SyncWriteDALProtocol",
    "escape_like",
    "filtered_in_sql_values",
]
