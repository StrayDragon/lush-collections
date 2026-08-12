# lush-sqlalchemyx — 子模块约定

> SQLAlchemy DAL 实现 + async/sync MySQL manager + 框架集成.

## 模块结构

```
src/lush_sqlalchemyx/
├── _compat.py                         # 可选依赖运行时检查 (asyncio)
├── base/dal/
│   ├── _common.py                     # async/sync 共享: 类型变量、Mixin、工具函数
│   ├── _async.py                      # Async DAL (RawRead/Read/Write/Base), 直接实现 ABC
│   ├── _sync.py                       # Sync DAL (RawRead/Read/Write/Base), 直接实现 ABC
│   ├── _dynamic.py                    # DynamicDAL: TableRef + DynamicSyncDAL/AsyncDAL (无 ORM Table class)
│   ├── _pagination.py                 # 分页工具
│   └── __init__.py                    # 统一导出
├── mgrs/mysql/
│   ├── manager.py / mapper.py         # Async MySQL Manager / Mapper
│   └── sync_manager.py / sync_mapper.py  # Sync 镜像
├── integrations/
│   ├── fastapi/depends/               # FastAPI DI
│   └── flask/ext.py                   # LushFlaskSQLAlchemy + FlaskSessionDALAdapter
└── shortcuts/meta.py                  # DDL 元数据工具
```

## DAL 设计

### 两条路径

1. **ORM DAL** (`_sync.py` / `_async.py`): 需要定义 `DeclarativeBase` 子类, 走 ORM Session 事件链 (软删除/只读自动拦截).
2. **Dynamic DAL** (`_dynamic.py`): 无需 ORM Table class, 用 `TableRef` + Pydantic CU/DTO + 表名直接操作, 走 SQLAlchemy Core. 软删除/只读在 DAL 方法层拦截.

### Dynamic DAL

- `TableRef`: 轻量表引用, `pk_column` 和 `columns` 均可选, 默认从 DTO 自动推导.
- `DynamicSyncDAL` / `DynamicAsyncDAL`: API 与 ORM DAL 对齐, 新增 `restore_by_id`.
- 软删除: SELECT 自动注入 `WHERE sd_col=0`, DELETE 转为 `UPDATE SET sd_col=1`.
- 只读: 写入操作前检查 `config.is_readonly`, 拒绝则抛 `TypeError`.
- 主键获取: `sa.table()` 不知道 PK 约束, 用 `result.lastrowid` 作为 fallback.
- 共享主键 / 显式 PK insert: `DynamicTableConfig(exclude_pk_on_create=False)` (update 仍始终排除 PK).

### 1:1 水平扩展表 (共享主键)

ORM 路径用 `EXTEND_TABLE_CU_CONFIG` (见 `lush-dal-protocol` `cu_config`); Dynamic 路径用 `exclude_pk_on_create=False`.
扩展表必须独立 DAL; 同事务: 主表 `ret_dto_after_create` → 扩展表 `ret_dto_after_create(cu_with_id)`.

### 单实现层

- **`_async.py` / `_sync.py`**: 单一实现层, 直接继承 `lush-dal-protocol` ABC (`AbstractAsyncReadDAL`, `AbstractAsyncWriteDAL` 等).
- ABC 定义 13 个通用方法 (Read 8 + Write 5), 无 `extra` 参数.
- ORM 特有方法 (Lock/AdvancedWrite/BatchField/RawSQL 等 ~12 个) 不在 ABC 中, 直接在实现层用 explicit kwargs 声明.

### 通用规则

- async 和 sync API **一一镜像**, 方法签名和行为语义一致.
- DAL 方法为 **classmethod**, 接收 `session` 作为第一参数.

## Conformance 测试

DAL 实现必须通过 `lush-dal-protocol` 的一致性套件 (Read+Write+FieldIsolation = Full):

```python
from lush_dal_protocol.testing import AsyncFullDALConformanceTests


class TestAsyncDALConformance(AsyncFullDALConformanceTests):
    def _post_write_refresh(self, session):
        session.expire_all()

    @pytest.fixture
    def dal_class(self):
        return MyDAL

    @pytest.fixture
    async def session(self, async_session):
        return async_session

    @pytest.fixture
    def sample_cu(self):
        return MyCU(name="test")

    @pytest.fixture
    def make_cu(self):
        return lambda label: MyCU(name=f"test-{label}")
```

## Flask-SQLAlchemy 集成 (两条路径)

1. **独立 Engine**: `LushFlaskSQLAlchemy` — 完全独立, 自建 Engine/Session.
2. **复用 db.session**: `FlaskSessionDALAdapter` — 桥接到 Flask request-scoped session, 适合渐进式迁移.

## 依赖

- 核心: `sqlalchemy>=2.0.21`, `pydantic`, `lush-dal-protocol>=0.5.0`, `lush-stdx`, `lush-pydanticx`
- 可选:
  - `[asyncio]`: `sqlalchemy[asyncio]>=2.0.43`
  - `[flask]`: `flask-sqlalchemy>=3.1.1`

## 测试策略

- **async DAL**: Docker MySQL (`LUSH_TEST_MYSQL_IMAGE`), 自动创建/销毁随机库名.
- **sync DAL**: SQLite (`:memory:` 或临时 `.db`), 无需外部依赖.
- **Flask 集成**: Flask test client + SQLite.
- **MySQL matrix**: `mysql:5.7` + `mysql:8.0.40-debian` (`just test-mysql-matrix` / CI workflow), 覆盖非严格 zero-date 与严格模式.
- 100% branch coverage, `--cov-fail-under=100`.

### BDD / Oracle 对拍

行为变更须先写 feature / oracle 测试, 再实现:

1. `.feature` 或单元测试描述语义
2. `tests/oracle/` 用原始 SQLAlchemy 实现期望语义
3. 被测 DAL API 与 oracle 对拍
4. 实现变绿

### update_only_set_by_id 与 None

- 默认 `none_policy="allow"` 保持与 0.7.0 兼容; 迁移全字段 CU 推荐显式传 `none_policy="ignore"`.
- `"allow"` / `"forbid"` 与 `update_partial_by_id` 对齐.
- `setattr` 与点号赋值在 ORM 上等价; 问题在脏字段是否进入 UPDATE, 不在赋值语法.

### Coverage Omit

无 omit 条目 — 所有源码均计入覆盖率.

### 公共 API 边界

- `_common.py` 中的双下划线事件监听器 (`__receive_before_flush`、`__add_filtering_criteria`、`__prevent_readonly_write`) 为内部实现细节，不通过 `__init__.py` re-export。
- `_pagination.py` 中的 `encode_cursor` / `decode_cursor` 为内部游标编解码工具，不暴露到公共 API。
- 测试如需访问这些内部函数，须使用 `getattr(module, "_CommonModule__<name>")` name-mangled 形式。

### basedpyright 规则

| 范围 | 规则 | 原因 |
|------|------|------|
| integrations/ | 放宽 unknown type 检查 | Flask/FastAPI 集成层类型推断受限 |

### pragma: no cover 用法

| 位置 | 原因 |
|------|------|
| `_async.py` L643 `return None` (已内联) | coverage.py 异步协程计量局限, 逻辑已由测试覆盖 |
| `_compat.py` ImportError 分支 | 可选依赖不存在时的 fast-fail 路径 |
| `_common.py` / `_async.py` / `_sync.py` TYPE_CHECKING 导入 | pyright 类型标注辅助 |
| `mgrs/mysql/mapper.py` / `sync_mapper.py` KeyError | 防御性 unreachable (dict 已预校验) |
| `_sync.py` RuntimeError | 重试循环的防御性 unreachable |
| `_sync.py` `hasattr` 检查 | 防御性类型守卫 |
| `integrations/flask/ext.py` ImportError | flask-sqlalchemy 可选依赖 |
| `shortcuts/meta.py` 文件级 | DDL 工具脚本, 非核心库运行时路径 |
| `_dynamic.py` `_db_col_to_val_key` L302 `field_info.alias` | Pydantic v2 会同步 alias→validation_alias, 此分支仅防御性保留 |
| `_dynamic.py` `DynamicSyncDAL.create` RuntimeError (pk 为 None / 读取失败) | 防御性 unreachable, SQLite INSERT 总能获取 PK 并读取 |
| `_dynamic.py` `DynamicAsyncDAL.create` L775-781 | coverage.py 异步协程计量局限, 逻辑已由 `test_create_and_get` 覆盖 |
| `_dynamic.py` `DynamicAsyncDAL.bulk_create` L846 `return len(rows)` | coverage.py 异步协程计量局限, 逻辑已由 `test_bulk_create` 覆盖 |

## 修改守则

- 新增/修改 DAL 方法: async 和 sync **必须同步更新**.
- ABC 方法签名必须匹配 `lush-dal-protocol` ABC, 否则 conformance 测试失败.
- ORM 特有方法 (不在 ABC 中) 使用 explicit kwargs, 不用 `extra` 参数对象.
- 新方法须加入 `__init__.py` 的 `__all__`.
- 可选依赖导入须经 `_compat.py` 的 `require_async()` 守卫.
- 不得用 `pragma: no cover` 跳过可测逻辑.
- **破坏性变更**: 必须在 `CHANGELOG.md` 中记录破坏性变更和重要变更.
- **提交前**: 运行 `ruff check` + `ruff format` + `basedpyright --level error` + 完整测试套件.
