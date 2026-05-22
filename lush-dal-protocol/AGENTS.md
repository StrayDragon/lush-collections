# lush-dal-protocol — 子模块约定

> ORM 无关的 DAL 抽象接口层 (分层 ABC + 参数对象).

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
| `params/lock.py` | `LockOptions` / `OptimisticLockOptions` — 锁操作参数对象 |
| `params/update.py` | `UpdateOptions` / `PartialUpdateOptions` — 更新操作参数对象 |
| `dto.py` | `BaseCU` / `BaseDTO` — ORM 无关 Pydantic 基类; `StdBaseCU` / `StdBaseDTO` (deprecated) |
| `errors.py` | `DBRetryableError` — 数据库并发可重试错误 |
| `utils/retry.py` | `RetryConfig` / `DEFAULT_RETRY_CONFIG` — 指数退避重试配置 |
| `utils/sql.py` | `filtered_in_sql_values` / `escape_like` — 通用工具函数 |
| `testing/conformance.py` | 分层一致性测试 mixin, 下游继承运行 |

## 一致性测试套件

`lush_dal_protocol.testing` 提供按层拆分的 mixin 测试类:

```python
from lush_dal_protocol.testing import SyncBaseDALConformanceTests

class TestMyDAL(SyncBaseDALConformanceTests):
    """继承一致性套件, 补充 session / model fixture."""
    ...
```

可用套件: `SyncReadDALConformanceTests`, `SyncWriteDALConformanceTests`, `SyncBaseDALConformanceTests` 及对应 Async 版本.

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
| `testing/conformance.py` | 一致性测试 mixin, 由下游继承运行, 自身仅验证可导入性 |

## 依赖

- 运行时: `pydantic>=2.3.0,<3.0.0`, `typing-extensions>=4.12.2`
- 开发: `pytest`, `pytest-asyncio`, `pytest-cov`
