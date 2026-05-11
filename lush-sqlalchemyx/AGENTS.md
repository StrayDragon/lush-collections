# lush-sqlalchemyx — 子模块约定

> SQLAlchemy DAL 实现 + async/sync MySQL manager + 框架集成.

## 模块结构

```
src/lush_sqlalchemyx/
├── _compat.py                         # 可选依赖运行时检查 (asyncio)
├── base/dal/
│   ├── _common.py                     # async/sync 共享: 类型变量、Mixin、工具函数
│   ├── _async.py                      # Async DAL 层 (RawRead/Read/Write/Base)
│   ├── _sync.py                       # Sync DAL 层 (RawRead/Read/Write/Base)
│   └── __init__.py                    # 统一导出 + lush-dal-protocol Protocol 重导出
├── mgrs/mysql/
│   ├── manager.py / mapper.py         # Async MySQL Manager / Mapper
│   └── sync_manager.py / sync_mapper.py  # Sync 镜像
├── integrations/
│   ├── fastapi/depends/               # FastAPI DI
│   └── flask/ext.py                   # LushFlaskSQLAlchemy + FlaskSessionDALAdapter
└── shortcuts/meta.py                  # DDL 元数据工具
```

## DAL 设计

- 实现 `lush-dal-protocol` Protocol (`SyncReadDALProtocol` / `AsyncWriteDALProtocol` 等).
- async 和 sync API **一一镜像**, 方法签名和行为语义一致.
- DAL 方法为 **classmethod**, 接收 `session` 作为第一参数.

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
- 新方法须加入 `__init__.py` 的 `__all__`.
- 可选依赖导入须经 `_compat.py` 的 `require_async()` 守卫.
- 不得用 `pragma: no cover` 跳过可测逻辑.
