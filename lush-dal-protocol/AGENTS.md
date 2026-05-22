# lush-dal-protocol — 子模块约定

> ORM 无关的 DAL 抽象接口层 (分层 ABC + Extra 扩展参数 + 一致性测试套件 + 内存参考实现).

## 定位

- **只声明 ABC 抽象接口**, 不包含具体 ORM 实现.
- **零 ORM 依赖**: 不允许导入 SQLAlchemy / Django ORM / Peewee 等.
- 下游包 (如 `lush-sqlalchemyx`) 依赖本包, 继承 ABC 并绑定泛型参数.

## 模块结构

| Module | 职责 |
|--------|------|
| `abc/read.py` | AbstractAsync/SyncReadDAL — 读操作 ABC (8 个 abstractmethod) |
| `abc/write.py` | AbstractAsync/SyncWriteDAL — 写操作 ABC (5 个 abstractmethod) |
| `abc/lock.py` | AbstractAsync/SyncLockDAL — 锁操作 ABC (4 个 abstractmethod) |
| `abc/batch_field.py` | AbstractAsync/SyncBatchFieldDAL — 批量字段查询 ABC (2 个 abstractmethod) |
| `abc/advanced_write.py` | AbstractAsync/SyncAdvancedWriteDAL — 高级写操作 ABC (4 个 abstractmethod) |
| `abc/raw_sql.py` | AbstractAsync/SyncRawSQLDAL — 原始 SQL ABC (2 个 abstractmethod) |
| `abc/composed.py` | AbstractAsync/SyncBaseDAL — Read + Write 组合 |
| `params/extra.py` | `Extra` 基类 + `ExtraT` TypeVar — 所有 API 的统一扩展参数 |
| `dto.py` | `BaseCU` / `BaseDTO` — ORM 无关 Pydantic 基类; `StdBaseCU` / `StdBaseDTO` (deprecated) |
| `errors.py` | `DBRetryableError` — 数据库并发可重试错误 |
| `utils/retry.py` | `RetryConfig` / `DEFAULT_RETRY_CONFIG` — 指数退避重试配置 |
| `utils/sql.py` | `filtered_in_sql_values` / `escape_like` — 通用工具函数 |
| `testing/conformance.py` | 分层一致性测试 mixin, 下游继承运行 |
| `testing/reference.py` | 内存参考实现 (InMemorySyncDAL/AsyncDAL), 验证套件正确性 |

## Extra 扩展参数

所有 ABC 方法的最后一个位置参数统一为 `extra: ExtraT | None = None`:

- `Extra` 是 `@dataclass(frozen=True)` 基类, 下游可继承添加 ORM 特有字段.
- `ExtraT = TypeVar("ExtraT", bound=Extra, default=Extra)` 支持默认泛型参数 (Python 3.10+).
- 取代了之前的 `LockOptions` / `UpdateOptions` 等分散参数对象.

## 一致性测试套件

`lush_dal_protocol.testing` 提供按层拆分的 mixin 测试类和内存参考实现:

```python
from lush_dal_protocol.testing import SyncFullDALConformanceTests

class TestMyDAL(SyncFullDALConformanceTests):
    @pytest.fixture
    def dal_class(self): return MyDAL
    @pytest.fixture
    def session(self): ...
    @pytest.fixture
    def sample_cu(self): return MyCU(name="test")
    @pytest.fixture
    def make_cu(self): return lambda label: MyCU(name=f"test-{label}")
    @pytest.fixture
    def where_clause_factory(self): ...
```

### Fixture 协议

| Fixture | 必须 | 说明 |
|---------|------|------|
| `dal_class` | 是 | 被测 DAL 类 (classmethod 风格) |
| `session` | 是 | ORM session (类型无约束, 由 hook 处理刷新) |
| `sample_cu` | 是 | 最简 CU 实例 |
| `make_cu` | Full 套件 | `Callable[[str], CU]`, 字段级隔离测试 |
| `where_clause_factory` | Lock 套件 | `Callable[[entity], list]`, 匹配过滤条件 |

### 内存参考实现

`testing/reference.py` 提供 `InMemorySyncDAL` / `InMemoryAsyncDAL`, 基于纯 Python 字典:
- 在本包测试中跑完整 conformance 套件, 证明测试本身的正确性.
- 为下游实现提供每个 ABC 方法的预期语义示例.

### 可用套件

| 粒度 | Sync | Async |
|------|------|-------|
| Read | `SyncReadDALConformanceTests` | `AsyncReadDALConformanceTests` |
| Write | `SyncWriteDALConformanceTests` | `AsyncWriteDALConformanceTests` |
| Base (R+W) | `SyncBaseDALConformanceTests` | `AsyncBaseDALConformanceTests` |
| Field Isolation | `SyncFieldIsolationDALConformanceTests` | `AsyncFieldIsolationDALConformanceTests` |
| Lock | `SyncLockDALConformanceTests` | `AsyncLockDALConformanceTests` |
| AdvancedWrite | `SyncAdvancedWriteDALConformanceTests` | `AsyncAdvancedWriteDALConformanceTests` |
| **Full** | `SyncFullDALConformanceTests` | `AsyncFullDALConformanceTests` |

### `_post_write_refresh` hook

写操作后的 session 刷新逻辑通过 `_post_write_refresh(self, session)` hook 方法抽象:

- 默认 **no-op** — 内存参考实现无需刷新.
- 下游 ORM 包覆写此方法实现各自的刷新逻辑:

```python
def _post_write_refresh(self, session):
    session.expire_all()   # SQLAlchemy 示例
```

> **重要**: 在调用 `_post_write_refresh` 之前, 必须先将后续需要的实体属性
> (如 `id`, `name`) 提取到本地变量, 避免 async session 的同步 lazy load 失败.

## 修改守则

- 修改 `abc/*.py` 方法签名/行为约定时, **必须同步更新** `testing/conformance.py` 对应测试.
- ABC 方法 docstring 必须中文.
- 每个 ABC 层的 abstractmethod 名称**全局唯一**, 不允许两个 ABC 定义同名方法.
- 新增 ABC 方法后, 下游 CI 应自动因一致性测试失败而暴露缺口.

## 测试 & 覆盖率

- 100% branch coverage, `--cov-fail-under=100`.
- ABC 的 `...` body 通过 `exclude_also = ["\\.\\.\\.""]` 排除.

### Coverage Omit

| Path | Reason |
|------|--------|
| `testing/conformance.py` | 一致性测试 mixin, 由下游和内存参考实现运行 |
| `testing/reference.py` | 内存参考实现, 属测试基础设施, 非生产代码 |

## 依赖

- 运行时: `pydantic>=2.3.0,<3.0.0`, `typing-extensions>=4.12.2`
- 开发: `pytest`, `pytest-asyncio`, `pytest-cov`
