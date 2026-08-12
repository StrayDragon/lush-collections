# Changelog

本文件记录 `lush-sqlalchemyx` 的破坏性变更和重要变更，帮助从低版本升级。

## Unreleased

### Changes

- 依赖 `lush-dal-protocol` `BaseCU.cu_config`: WriteDAL update 路径改读 `update_exclude`; 导出 `BaseCUConfigDict` / `EXTEND_TABLE_CU_CONFIG`
- `DynamicTableConfig.exclude_pk_on_create` (默认 `True`); update 经 `cu_row_data(..., for_create=False)` 始终排除 PK
- 支持 1:1 水平扩展表 (共享主键) ORM / Dynamic 双路径

## 0.7.1

### Changes

- `update_only_set_by_id` / `ret_dto_after_update_by_id` (async + sync) 与 Flask adapter 新增 `none_policy` 参数
- 默认 `none_policy="allow"`, 保持与 0.7.0 行为一致; 迁移全字段 CU 推荐显式传 `none_policy="ignore"`
- 新增 MySQL 5.7 / 8 matrix 集成测试 (sync + async) 与非严格 `sql_mode` 复现基建
- 导出 `NonePolicy` 类型别名

## 0.7.0

### Breaking Changes

**移除 SQLAlchemy Repository 层**

| 被移除的符号 | 说明 | 替代方案 |
|---|---|---|
| `SyncSQLAlchemyRepository` | 与 DAL 语义冲突的第二套 CRUD | 使用 `SyncBaseDAL` + 显式 session |
| `AsyncSQLAlchemyRepository` | 同上 | 使用 `AsyncBaseDAL` + 显式 session |

分页语句工具 (`build_offset_stmt` / `build_cursor_stmt` / `make_*_result`) 保留.

**移除内部实现细节的公共导出**

以下符号不再从 `lush_sqlalchemyx.base.dal` 导出，属于框架内部实现细节：

| 被移除的符号 | 说明 | 替代方案 |
|---|---|---|
| `__prevent_readonly_write` | 只读保护事件监听器 | 通过 `setup_dal_hooks()` 注册，无需直接访问 |
| `__receive_before_flush` | 软删除事件监听器 | 通过 `setup_dal_hooks()` 注册，无需直接访问 |
| `encode_cursor` | 游标 base64 编码 | 内部实现，由 `CursorResult.next_cursor` 自动处理 |
| `decode_cursor` | 游标 base64 解码 | 内部实现，由 `CursorPagination.cursor` 自动处理 |

如果你的代码依赖这些符号，需要改为从内部路径导入：
```python
# 不推荐（内部路径可能变更）
from lush_sqlalchemyx.base.dal._pagination import encode_cursor, decode_cursor
from lush_sqlalchemyx.base.dal._common import __prevent_readonly_write
```

### Changes

- 错误/工具类型从 `lush-dal-protocol` re-export (`DBRetryableError`, `filtered_in_sql_values` 等), 消除重复定义
- `SoftDeleteTableMixin.soft_delete_loader_criteria()` — 自定义软删除列可覆写 loader 谓词
- ORM / DynamicAsync conformance 升至 Full 套件
- 新增 `tests/oracle/` Core SQL 对拍基建 (不依赖 DAL hooks)
- 依赖下限提升至 `lush-dal-protocol>=0.5.0`
- `AGENTS.md` 移除 Repository 模块; 补充 oracle 测试约定; 新增"公共 API 边界"章节

## 0.6.0

### Breaking Changes

**移除 `Std*` 预设业务字段类**

以下类已被移除（原已标记 `deprecated`）：

| 被移除的类 | 替代方案 |
|---|---|
| `StdBaseCU` | 继承 `BaseCU`，自行声明需要的字段 |
| `StdBaseDTO` | 继承 `BaseDTO`，自行声明需要的字段 |
| `StdAsyncBaseTable` | 继承 `BasicAsyncBaseTable`，自行声明需要的字段 |
| `StdReadOnlyBasicAsyncBaseTable` | 继承 `ReadOnlyBasicAsyncBaseTable`，自行声明需要的字段 |
| `StdSyncBaseTable` | 继承 `BasicSyncBaseTable`，自行声明需要的字段 |
| `StdReadOnlySyncBaseTable` | 继承 `ReadOnlySyncBaseTable`，自行声明需要的字段 |

```python
# 旧方式 (已删除)
from lush_sqlalchemyx.base.dal import StdAsyncBaseTable, StdBaseCU


class MyTable(StdAsyncBaseTable):
    __tablename__ = "my_table"
    name: Mapped[str] = mapped_column(sa.String(50))
    # create_operator_id, update_operator_id, is_delete 自动来自 StdAsyncBaseTable


# 新方式
from lush_sqlalchemyx.base.dal import BasicAsyncBaseTable, BaseCU


class MyTable(BasicAsyncBaseTable):
    __tablename__ = "my_table"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(50))
    create_operator_id: Mapped[int] = mapped_column(sa.Integer, default=0)
    is_delete: Mapped[int] = mapped_column(sa.SmallInteger, default=0)
```

**`is_delete` 列类型变更**

`FieldIsDeleteSoftDeleteTableMixin.is_delete` 列类型从 `Integer` 改为 `SmallInteger`。

已有表需要执行 DDL 迁移：
```sql
-- MySQL
ALTER TABLE <your_table> MODIFY COLUMN is_delete SMALLINT NOT NULL DEFAULT 0;

-- PostgreSQL
ALTER TABLE <your_table> ALTER COLUMN is_delete TYPE SMALLINT;
```

### Changes

- 新增 `MySQLPoolConfig` 可配置连接池
- `shortcuts/meta.py` 清理 DDL 字段排序偏好

## 0.4.2

### Breaking Changes

**移除 `@sa_event.listens_for` 隐式钩子注册**

`import lush_sqlalchemyx` 不再自动注册 Session 事件监听器，必须显式调用 `setup_dal_hooks()`。

```python
from lush_sqlalchemyx import setup_dal_hooks

setup_dal_hooks()
```

按框架调用指引：
- **Flask**: 使用 `LushFlaskSQLAlchemy.init_db()` 自动注册
- **FastAPI**: 在 `lifespan` 中调用 `setup_dal_hooks()`
- **直接使用 DAL**: 在创建 Session 前调用一次

## 0.4.0

### Breaking Changes

**`SoftDeleteTableMixin` 拆分为两层**

```python
# 旧方式
from lush_sqlalchemyx.base.dal import SoftDeleteTableMixin

# 新方式
from lush_sqlalchemyx.base.dal import FieldIsDeleteSoftDeleteTableMixin
```

**方法重命名**

| 旧方法 | 新方法 |
|--------|--------|
| `.delete(is_delete=1)` | `.soft_delete()` |
| `.delete(n)` | 不再支持自定义值 |
| `.undelete()` | `.soft_undelete()` |

### Changes

- 新增 `setup_dal_hooks()` 一次调用注册所有必要钩子（幂等）
- 新增 `register_soft_delete_hooks()` / `unregister_soft_delete_hooks()` / `is_soft_delete_hooks_registered()`
- `SoftDeleteTableMixin` 现在是纯协议基类，支持自定义软删除列
