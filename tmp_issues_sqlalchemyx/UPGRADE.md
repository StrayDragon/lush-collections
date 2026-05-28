# Upgrade Guide: lush-sqlalchemyx 软删除修复

## 版本变更

| 版本 | 变更 |
|------|------|
| 0.3.3 | 修复软删除 Session 钩子注册机制 + `get_by_id`/`exists`/`ret_dto_after_get_by_id` `is_delete` 守卫 |

## 问题修复

### 1. Session 钩子未注册 → 静默物理删除（严重）

**旧行为**：`import lush_sqlalchemyx` 不会注册软删除钩子。用户需间接 import `base.dal._common` 才能触发。未注册时 `delete_by_id` 执行物理 DELETE。

**新行为**：`import lush_sqlalchemyx` 自动注册软删除钩子（`before_flush` + `do_orm_execute`）。

**升级迁移**：无需任何改动。原有依赖 `lush-sqlalchemyx` 的代码在升级后自动获得钩子注册。

### 2. `get_by_id`/`exists`/`ret_dto_after_get_by_id` 软删后不一致

**旧行为**：`session.get()` 命中 identity map，软删后的实体仍被返回（`is_delete=1`）。

**新行为**：上述三个方法在 `session.get()` 后检查 `isinstance(entity, SoftDeleteTableMixin) and entity.is_delete`，已软删时返回 `None`/`False`。

## 新增公开 API

| 函数 | 说明 |
|------|------|
| `setup_dal_hooks()` | **首选** — 一次调用注册所有必要钩子（幂等），用户无需关注细节 |
| `register_soft_delete_hooks()` | 显式注册软删除钩子（幂等） |
| `unregister_soft_delete_hooks()` | 注销软删除钩子（幂等） |
| `is_soft_delete_hooks_registered()` | 检查钩子是否已注册 |

从以下路径均可导入：

```python
from lush_sqlalchemyx import register_soft_delete_hooks
from lush_sqlalchemyx.base.dal import register_soft_delete_hooks
```

## 推荐最佳实践

### FastAPI

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from lush_sqlalchemyx import setup_dal_hooks


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_dal_hooks()  # 一次调用注册所有钩子
    yield


app = FastAPI(lifespan=lifespan)
```

### Flask

```python
from flask import Flask
from lush_sqlalchemyx import setup_dal_hooks


def create_app():
    app = Flask(__name__)
    setup_dal_hooks()  # 一次调用注册所有钩子
    return app
```

### 测试

```python
from lush_sqlalchemyx import register_soft_delete_hooks, unregister_soft_delete_hooks


def test_something():
    register_soft_delete_hooks()
    # ... 测试逻辑 ...
    unregister_soft_delete_hooks()
```

## 降级/回退

如因兼容性问题需降级，保留 `lush-sqlalchemyx<0.3.3` 版本锁定即可。

```toml
# pyproject.toml
dependencies = [
    "lush-sqlalchemyx>=0.3.0,<0.3.3",
]
```
