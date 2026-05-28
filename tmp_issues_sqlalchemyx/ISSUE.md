# lush-sqlalchemyx: 软删 Session 钩子与 `get_by_id` 语义问题

| 项 | 值 |
|----|-----|
| 包 | `lush-sqlalchemyx`（验证版本 `0.3.2`） |
| 复现 | 本目录 `repro.py`（单文件，SQLite `:memory:`，无 Flask / pytest） |
| 严重性 | **高**（钩子未注册 → 静默物理删） / **中**（钩子已注册但 `get_by_id` 与 `get_all` 不一致） |

---

## 依赖

```text
lush-sqlalchemyx>=0.3.2
sqlalchemy>=2.0
pydantic>=2
```

---

## 运行复现（复制整个目录即可）

```bash
cd lush_upstream_issue   # 复制本目录到任意位置

# 需已安装 lush-sqlalchemyx / sqlalchemy / pydantic
python repro.py positive          # 问题 1
python repro.py hooks-missing     # 问题 2（严重）
python repro.py no-select-filter  # 问题 2b
python repro.py all               # 全部
```

不依赖 pytest、Flask、MySQL；**不依赖 service_user 代码**（单文件 `repro.py`）。

退出码 **0** = 观测到下文描述的行为（issue 仍存在）。  
退出码 **非 0** = 未复现（可能已修复）或环境不符。

### 建议在 MySQL 环境复测

SQLite 足以复现 ORM / Session 语义；合并前请在 **MySQL + 实际 Session 配置**（如 Flask-SQLAlchemy `scoped_session`）下再确认一次。  
业务侧可参考：`revised_bill` 模块 + `is_delete` 为 `TINYINT` 的表。

---

## 问题 1：钩子已注册 — `get_by_id` / `exists` 与 `get_all` / `select` 不一致

**触发**：`entity = dal.create(cu)` → `dal.delete_by_id(entity.id)` → 仍持有 `entity` 引用。

| 读路径 | 软删后（identity map 仍有实例） |
|--------|--------------------------------|
| `select()` / `get_all()` | 不包含已删行 ✓ |
| `session.get` / `get_by_id` / `exists` | **仍可能返回** `is_delete=1` 的对象 ✗ |
| 裸 SQL | 行在，`is_delete=1` ✓ |

**期望**：`get_by_id` / `exists` 与 `get_all` 一致（或文档明确禁止删后使用）。

**lush 源码**：`SyncReadDAL.get_by_id` → `session.get(...)`（`_sync.py`）；过滤在 `do_orm_execute`（`_common.py`），不作用于 identity map 命中。

---

## 问题 2：Session 钩子未注册 — 软删静默失效（非常严重）

`SoftDeleteTableMixin` 单独继承 **不够**。须注册 `SyncSession` 全局监听（当前在 `import lush_sqlalchemyx.base.dal._common` 时副作用注册）：

| 钩子 | 缺失时 |
|------|--------|
| `before_flush` | `delete` → **物理 DELETE**，行消失 |
| `do_orm_execute` | `select` / `get_all` **不过滤** `is_delete=1` |

**无异常、无日志**。用户以为继承 mixin 即安全。

### 常见误用

- 应用/测试从未 `import lush_sqlalchemyx.base.dal`
- 多进程 worker 子进程未加载 dal
- 测试自建 `Session`，未走应用启动链

### 库侧建议（优先）

1. **包 import 时自动幂等注册钩子**；未注册则 **fail-fast**（warning / ImportError）
2. 提供公开 API：`register_soft_delete_session_hooks()`，勿依赖隐式 import
3. 修复问题 1：`get_by_id` 改走 `select` 或文档约束

---

## 提交上游时可附

- 本 `ISSUE.md`
- `python repro.py all` 完整终端输出
- `pip show lush-sqlalchemyx` 版本
