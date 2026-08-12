# Changelog

本文件记录 `lush-dal-protocol` 的破坏性变更和重要变更，帮助从低版本升级。

## Unreleased

### Changes

- 新增 `pk_field_cu_config(pk_field, *, keep_on_create=False)`; `EXTEND_TABLE_CU_CONFIG` 改为其 `keep_on_create=True` 别名 (显式含 `update_exclude`)
- `BaseCU` 新增 `cu_config` / `BaseCUConfigDict` / `EXTEND_TABLE_CU_CONFIG` (对标 Pydantic `ConfigDict` k=v 写法)
- `to_orm_model` 与 InMemory create/update dump 分别尊重 `to_orm_exclude` / `update_exclude` (MRO 浅合并, 类创建期缓存)
- InMemory `_insert`: dump 含客户端 `id` 时采用该主键; 重复 id 抛 `ValueError`; 推进 `_next_id`

## 0.5.0

### Breaking Changes

**移除 Repository ABC**

| 被移除的符号 | 说明 |
|---|---|
| `AbstractSyncRepository` | 无下游实现使用, 已删除 |
| `AbstractAsyncRepository` | 无下游实现使用, 已删除 |
| `examples/example_03_repository.py` | 对应示例已删除 |

分页类型 (`OffsetPagination` / `PageResult` 等) 保留, 供 DAL 与分页工具使用.

### Changes

- `AGENTS.md` 修正 conformance 套件文档: 删除不存在的 Lock/AdvancedWrite 套件行; 注明 Full = Read+Write+FieldIsolation
- 导出 `SyncFullDALConformanceTests` / `AsyncFullDALConformanceTests`

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
