# lush-dalx — 子模块约定

> ORM 无关的 DAL 协议抽象层 (纯接口薄层).

## 定位

- **只声明 Protocol / Interface**, 不包含具体 ORM 实现.
- **零 ORM 依赖**: 不允许导入 SQLAlchemy / Django ORM / Peewee 等.
- 下游包 (如 `lush-sqlalchemyx`) 依赖本包并实现协议.

## 模块结构

| Module | 职责 |
|--------|------|
| `protocols.py` | Sync/Async Read/Write/Base DAL Protocol (含中文 docstring 行为约定) |
| `dto.py` | `BaseCU` / `BaseDTO` / `StdBaseCU` / `StdBaseDTO` — ORM 无关 Pydantic 基类 |
| `errors.py` | `DBRetryableError` — 数据库并发可重试错误 |
| `retry.py` | `RetryConfig` / `DEFAULT_RETRY_CONFIG` — 指数退避重试配置 |
| `utils.py` | `filtered_in_sql_values` / `escape_like` — 通用工具函数 |
| `testing.py` | `SyncDALConformanceTests` / `AsyncDALConformanceTests` — 一致性测试 mixin |

## 一致性测试套件

`lush_dalx.testing` 提供 mixin 测试类, 下游实现 **必须** 继承并运行:

```python
from lush_dalx.testing import SyncDALConformanceTests

class TestMyDAL(SyncDALConformanceTests):
    """继承一致性套件, 补充 session / model fixture."""
    ...
```

### 下游接入流程

1. `pyproject.toml` 添加依赖: `lush-dalx>=0.1.0`
2. 实现 `lush_dalx.protocols` 中声明的 Sync/Async DAL Protocol
3. 测试中继承 `SyncDALConformanceTests` (或 Async 版本), 提供 fixture, 运行一致性验证

## 修改守则

- 修改 `protocols.py` 方法签名/行为约定时, **必须同步更新** `testing.py` 对应测试方法.
- Protocol 方法 docstring 必须中文, 包含: 参数说明、返回值、行为约定.
- 新增 Protocol 方法后, 下游 CI 应自动因一致性测试失败而暴露缺口.

## 测试 & 覆盖率

- 100% branch coverage, `--cov-fail-under=100`.
- Protocol 的 `...` body 通过 `exclude_also = ["\\.\\.\\.""]` 排除.

### Coverage Omit

| Path | Reason |
|------|--------|
| `testing.py` | 一致性测试 mixin, 由下游继承运行, 自身仅验证可导入性 |

## 依赖

- 运行时: `pydantic>=2.11.0,<3.0.0`, `typing-extensions>=4.12.2`
- 开发: `pytest`, `pytest-asyncio`, `pytest-cov`
