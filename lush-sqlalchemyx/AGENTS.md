# lush-sqlalchemyx — 子模块约定

> SQLAlchemy DAL 实现 + async/sync MySQL manager + 框架集成.

## 模块结构

```
src/lush_sqlalchemyx/
├── _compat.py                         # 可选依赖运行时检查 (asyncio)
├── base/dal/
│   ├── _common.py                     # async/sync 共享: 类型变量、Mixin、工具函数
│   ├── _async.py                      # Async DAL V1 层 (RawRead/Read/Write/Base)
│   ├── _sync.py                       # Sync DAL V1 层 (RawRead/Read/Write/Base)
│   ├── _async_v2.py                   # Async DAL V2 — 实现 lush-dal-protocol ABC
│   ├── _sync_v2.py                    # Sync DAL V2 — 实现 lush-dal-protocol ABC
│   ├── _params.py                     # SQLAExtra (继承 Extra) — SQLAlchemy 扩展参数
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

### V1/V2 双轨策略

- **V1** (`_async.py` / `_sync.py`): 原始实现, 保持向后兼容.
- **V2** (`_async_v2.py` / `_sync_v2.py`): 实现 `lush-dal-protocol` ABC, 内部委托 V1 核心逻辑.
- V2 类继承 V1 类 + ABC, 方法签名使用 `extra: SQLAExtra | None = None` 统一扩展参数.
- 下游逐步迁移到 V2, V1 保持可用.

### SQLAExtra

`SQLAExtra(Extra)` 是 SQLAlchemy 特有的扩展参数, 继承自 `lush-dal-protocol` 的 `Extra`:

```python
@dataclass(frozen=True)
class SQLAExtra(Extra):
    lock_timeout: int | None = None
    need_refresh: bool = False
    version_field: str = "version"
    strict_missing: bool = True
    none_policy: Literal["ignore", "allow", "forbid"] = "ignore"
    # ...
```

### 通用规则

- async 和 sync API **一一镜像**, 方法签名和行为语义一致.
- DAL 方法为 **classmethod**, 接收 `session` 作为第一参数.

## Conformance 测试

V2 DAL 必须通过 `lush-dal-protocol` 的完整一致性套件:

```python
from lush_dal_protocol.testing import AsyncFullDALConformanceTests

class TestAsyncDALV2Conformance(AsyncFullDALConformanceTests):
    def _post_write_refresh(self, session):
        session.expire_all()

    @pytest.fixture
    def dal_class(self): return MyV2DAL
    @pytest.fixture
    async def session(self, async_session): return async_session
    @pytest.fixture
    def sample_cu(self): return MyCU(name="test")
    @pytest.fixture
    def make_cu(self): return lambda label: MyCU(name=f"v2-{label}")
    @pytest.fixture
    def where_clause_factory(self): ...
```

## Flask-SQLAlchemy 集成 (两条路径)

1. **独立 Engine**: `LushFlaskSQLAlchemy` — 完全独立, 自建 Engine/Session.
2. **复用 db.session**: `FlaskSessionDALAdapter` — 桥接到 Flask request-scoped session, 适合渐进式迁移.

## 依赖

- 核心: `sqlalchemy>=2.0.21`, `pydantic`, `lush-dal-protocol>=0.1.0`, `lush-stdx`, `lush-pydanticx`
- 可选:
  - `[asyncio]`: `sqlalchemy[asyncio]>=2.0.43`
  - `[flask]`: `flask-sqlalchemy>=3.1.1`

## 测试策略

- **async DAL**: Docker MySQL (`LUSH_TEST_MYSQL_IMAGE`), 自动创建/销毁随机库名.
- **sync DAL**: SQLite (`:memory:` 或临时 `.db`), 无需外部依赖.
- **Flask 集成**: Flask test client + SQLite.
- 100% branch coverage, `--cov-fail-under=100`.

### Coverage Omit

无 omit 条目 — 所有源码均计入覆盖率.

### Ruff per-file-ignores

| Pattern | Rule | Reason |
|---------|------|--------|
| `**/dal/_*_v2.py` | `ARG003` | `extra` 参数由 ABC 签名要求但 V2 委托 V1 时不直接使用 |

### basedpyright 规则

| 范围 | 规则 | 原因 |
|------|------|------|
| 全局 | `reportImplicitOverride = false` | V1/V2 双轨策略, 方法覆写无需 `@override` |
| V2 ReadDAL 类 | `# pyright: ignore[reportIncompatibleMethodOverride]` | V1+ABC 双继承签名冲突 (extra 参数) |
| integrations/ | 放宽 unknown type 检查 | Flask/FastAPI 集成层类型推断受限 |

### pragma: no cover 用法

| 位置 | 原因 |
|------|------|
| `_async.py` L643 `return None` | coverage.py 异步协程计量局限, 逻辑已由测试覆盖 |
| `_compat.py` ImportError 分支 | 可选依赖不存在时的 fast-fail 路径 |
| `_common.py` / `_async.py` / `_sync.py` TYPE_CHECKING 导入 | pyright 类型标注辅助 |
| `mgrs/mysql/mapper.py` / `sync_mapper.py` KeyError | 防御性 unreachable (dict 已预校验) |
| `_sync.py` L89 RuntimeError | 重试循环的防御性 unreachable |
| `_sync.py` L790 `hasattr` 检查 | 防御性类型守卫 |
| `integrations/flask/ext.py` ImportError | flask-sqlalchemy 可选依赖 |
| `shortcuts/meta.py` 文件级 | DDL 工具脚本, 非核心库运行时路径 |

## 修改守则

- 新增/修改 DAL 方法: async 和 sync **必须同步更新**.
- V2 方法签名必须匹配 `lush-dal-protocol` ABC, 否则 conformance 测试失败.
- 新方法须加入 `__init__.py` 的 `__all__`.
- 可选依赖导入须经 `_compat.py` 的 `require_async()` 守卫.
- 不得用 `pragma: no cover` 跳过可测逻辑.
