# Changelog

本文件记录 `lush-dal-protocol` 的破坏性变更和重要变更，帮助从低版本升级。

## 0.4.0

### Breaking Changes

**`Base*` 协议重命名为 `Dto*`**

所有 `Base*` 前缀的 DAL 协议类已重命名为 `Dto*` 前缀，消除与 Pydantic `BaseModel` 的命名混淆。

| 旧名称 | 新名称 |
|--------|--------|
| `BaseSyncReadDAL` | `DtoSyncReadDAL` |
| `BaseAsyncReadDAL` | `DtoAsyncReadDAL` |
| `BaseSyncWriteDAL` | `DtoSyncWriteDAL` |
| `BaseAsyncWriteDAL` | `DtoAsyncWriteDAL` |
| `BaseSyncBaseDAL` | `DtoSyncDAL` |
| `BaseAsyncBaseDAL` | `DtoAsyncDAL` |

**测试 mixin 重命名**

| 旧名称 | 新名称 |
|--------|--------|
| `BaseSyncReadDALConformanceTests` | `SyncReadDALConformanceTests` (不变) |

Entity* 前缀的 conformance 测试 mixin 名称不变。

**文件重命名**

| 旧路径 | 新路径 |
|--------|--------|
| `abc/base_read.py` | `abc/dto_read.py` |
| `abc/base_write.py` | `abc/dto_write.py` |
| `abc/base_composed.py` | `abc/dto_composed.py` |
| `testing/base_conformance.py` | `testing/dto_conformance.py` |

### Changes

- 新增 `Dto*` 协议层，适用于 Core DAL / 非 ORM 场景
- 新增 `NoSession` / `NoEntity` 哨兵类型及对应单例 `NO_SESSION` / `NO_ENTITY`
- 新增 `DtoSyncConformanceTests` / `DtoAsyncConformanceTests` 等 mixin

## 0.2.2

### Changes

- 依赖 `lush-dal-protocol>=0.2.2` 的下游包（如 `lush-sqlalchemyx`）需要同步升级
