"""分层 DAL 一致性验证测试套件.

提供两部分能力:

1. **Conformance 测试 mixin** — 下游 ORM 适配包继承后注入 fixture 即可验证 ABC 实现.
2. **InMemory 参考实现** — 基于纯 Python 数据结构的完整 DAL, 用于验证套件正确性并作为下游示例.

测试套件分两层:

- **Entity* conformance** (``conformance.py``) — 验证 ``AbstractSyncReadDAL`` / ``AbstractSyncWriteDAL`` 等 ORM 风格协议.
- **Dto* conformance** (``dto_conformance.py``) — 验证 ``DtoSyncDAL`` / ``DtoAsyncDAL`` 等无 ORM 协议.
"""

from .conformance import (
    AsyncBaseDALConformanceTests,
    AsyncFieldIsolationDALConformanceTests,
    AsyncFullDALConformanceTests,
    AsyncReadDALConformanceTests,
    AsyncWriteDALConformanceTests,
    SyncBaseDALConformanceTests,
    SyncFieldIsolationDALConformanceTests,
    SyncFullDALConformanceTests,
    SyncReadDALConformanceTests,
    SyncWriteDALConformanceTests,
)
from .dto_conformance import (
    DtoAsyncConformanceTests,
    DtoAsyncFieldIsolationConformanceTests,
    DtoAsyncFullConformanceTests,
    DtoAsyncReadConformanceTests,
    DtoAsyncWriteConformanceTests,
    DtoSyncConformanceTests,
    DtoSyncFieldIsolationConformanceTests,
    DtoSyncFullConformanceTests,
    DtoSyncReadConformanceTests,
    DtoSyncWriteConformanceTests,
)
from .reference import (
    InMemoryAsyncDAL,
    InMemoryCU,
    InMemoryDTO,
    InMemoryEntity,
    InMemorySession,
    InMemorySyncDAL,
)

__all__ = [
    # Entity* conformance (ORM 风格)
    "AsyncBaseDALConformanceTests",
    "AsyncFieldIsolationDALConformanceTests",
    "AsyncFullDALConformanceTests",
    "AsyncReadDALConformanceTests",
    "AsyncWriteDALConformanceTests",
    # Dto* conformance (无 ORM 风格)
    "DtoAsyncConformanceTests",
    "DtoAsyncFieldIsolationConformanceTests",
    "DtoAsyncFullConformanceTests",
    "DtoAsyncReadConformanceTests",
    "DtoAsyncWriteConformanceTests",
    "DtoSyncConformanceTests",
    "DtoSyncFieldIsolationConformanceTests",
    "DtoSyncFullConformanceTests",
    "DtoSyncReadConformanceTests",
    "DtoSyncWriteConformanceTests",
    # InMemory 参考实现
    "InMemoryAsyncDAL",
    "InMemoryCU",
    "InMemoryDTO",
    "InMemoryEntity",
    "InMemorySession",
    "InMemorySyncDAL",
    "SyncBaseDALConformanceTests",
    "SyncFieldIsolationDALConformanceTests",
    "SyncFullDALConformanceTests",
    "SyncReadDALConformanceTests",
    "SyncWriteDALConformanceTests",
]
