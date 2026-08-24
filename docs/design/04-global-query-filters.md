# 04 — 全局查询过滤器泛化 (软删除机制归一化)

> 状态: **提案 (未实现)**
> 影响包: `lush-sqlalchemyx` (`_common.py` 事件层重构; 公共 API 零变化)
> 关联现状: `__add_filtering_criteria` 硬编码 `SoftDeleteTableMixin`; `with_loader_criteria` 注入

## 背景与动机

现有软删除实现本质是一个 **EF Core 式 HasQueryFilter 框架**:

- `do_orm_execute` 事件 + `with_loader_criteria(mixin, criteria_fn, include_aliases=True)` → 一切 SELECT (含 relationship load) 自动注入谓词
- 但该框架目前**只为软删除服务**, mixin 类型与谓词硬编码在 `_common.py`

同类需求 (多租户隔离、草稿可见性、按 env 过滤) 都需要"隐形 WHERE", 现状只能每个查询手写.
目标: 把机制泛化为注册表, 软删除成为第一个用户而非特例.

## 假想使用示例

### 库内部: 软删除自注册 (重构后公共行为零变化)

```python
# _common.py 内部 (示意):
register_global_filter(GlobalFilterSpec(
    mixin=SoftDeleteTableMixin,
    criteria=lambda cls: cls.soft_delete_loader_criteria(),
))
# 对外: SoftDeleteTableMixin / include_soft_deleted / setup_dal_hooks 全部不变
```

### 用户侧: 多租户隔离

```python
from contextvars import ContextVar
from lush_sqlalchemyx.base.dal import TenantScopedMixin, set_tenant_provider  # 假想

_current_tenant: ContextVar[int | None] = ContextVar("current_tenant", default=None)

class OrderTable(Base, TenantScopedMixin):     # mixin 提供 tenant_id 列 + 注册钩子
    __tablename__ = "order"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    amount: Mapped[int]
    tenant_id: Mapped[int]

# 应用启动时:
set_tenant_provider(lambda: _current_tenant.get())
setup_dal_hooks()   # 现有入口不变, 自动装载全部已注册过滤器
```

使用效果 — 业务代码完全无感知:

```python
async with session_factory() as session:
    token = _current_tenant.set(42)
    orders = (await session.execute(sa.select(OrderTable))).scalars().all()
    # SQL: SELECT ... FROM "order" WHERE tenant_id = 42      ← 自动注入
    # relationship load 同样被过滤 (include_aliases=True 的既有能力)

    _current_tenant.reset(token)
```

**fail-closed 效果** (关键安全语义):

```python
async with session_factory() as session:
    # 忘记设置租户上下文:
    await session.execute(sa.select(OrderTable))
    # → raise LookupError("租户上下文未初始化, 已拒绝执行可能跨租户的查询")
    # 而不是静默放行全表!
```

旁路显式且可审计:

```python
stmt = sa.select(OrderTable).execution_options(include_global_filters=True)   # 新通用开关
stmt = sa.select(OrderTable).execution_options(include_soft_deleted=True)     # 旧开关保留为别名
# 二者最终是同一个 execution option 键
```

### Dynamic 路径对应物

```python
ref = TableRef.of(
    "order", OrderDTO,
    config=DynamicTableConfig(
        soft_delete_column="is_delete",
        extra_select_filters=(lambda: order_owner_col == current_user_id(),),  # 假想: callable 或 ColumnElement 序列
    ),
)
# apply_select_filter 在软删谓词后追加 extra filters
```

### 通用注册 API (库内 + 高级用户)

```python
TMixin = TypeVar("TMixin", bound=type)

@dataclass(frozen=True, slots=True)          # 严格化约定见 [11 §3](./11-typing-test-rigor.md)
class GlobalFilterSpec(Generic[TMixin]):
    mixin: type[TMixin]                      # with_loader_criteria 锚点 (isinstance 匹配)
    criteria: Callable[[type[TMixin]], ColumnElement[bool]]   # 类 → 谓词; 泛型化后 lambda 内可静态访问 mixin 的列

def register_global_filter(spec: GlobalFilterSpec) -> None: ...
def unregister_global_filter(mixin: type) -> None: ...      # 测试隔离用, 与软删钩子管理 API 风格对齐
```

泛型化的实际收益: 注册租户过滤器时 `lambda cls: cls.tenant_id == current_tenant()`
里的 `cls.tenant_id` 能被 basedpyright 解析 (而非 unknown attribute)。
```

## 预期语义与效果

| 场景 | 重构前 | 重构后 |
|------|--------|--------|
| 软删表 SELECT | 自动过滤 | 完全一致 (回归回归底线) |
| 租户表 SELECT | 手写 WHERE | 自动注入 + fail-closed |
| relationship load | 软删自动过滤 | 所有注册过滤器一并生效 |
| `include_soft_deleted=True` | 跳过软删谓词 | 保持; 等价新名 `include_global_filters` |
| 写操作 (INSERT/UPDATE/DELETE) | 仅只读守卫拦截 | **一期不拦截** (见决策 #3) |
| 未注册任何过滤器 | — | 行为等同现状裸查询 |
| 运行时开销 (所有场景) | 每条语句 O(k) 谓词评估 (k=已注册过滤器数, 常数级) | 谓词全部下推 SQL, **无行级 Python 开销**; 注册/注销本身 O(1) 幂等操作 |

## 待决策项 (Open Decisions)

| # | 决策点 | 当前倾向 |
|---|--------|----------|
| 1 | 上下文缺失时 fail-open 还是 fail-closed | **fail-closed 默认**. 这是库能替用户防的最高价值易错陷阱 (foot-gun); provider 可声明自己的 fallback |
| 2 | bypass 开关形态 | 单一 execution option 双名兼容; 文档标注旧名为软删时代遗留 |
| 3 | 写侧守卫 (防跨租户 INSERT/UPDATE 的 before_flush 泛化) | **二期**. 一期只动读路径, 控制重构的影响范围 (blast radius) |
| 4 | `TenantScopedMixin` 是否进库 | 进 (作为参考实现), 但 provider 函数必须用户注入 — 库不假设租户来源 (header/JWT/连接属性) |
| 5 | 注册表可见性 | 参照软删钩子管理 API 风格: 显式 register/unregister/is_registered 三件套, 幂等 |

## 测试策略 (纯重构 + 增量)

1. **回归回归底线**: 现有 `tests/oracle/soft_delete.py` 与全部软删相关测试原样通过, 一个断言都不改
2. 注册表单测: register/unregister 幂等性、多过滤器叠加顺序确定性
3. 租户场景 oracle 对比测试: 上下文已设/未设/bypass 三态的 SQL 断言
4. Dynamic 路径: extra filters 与 soft delete 谓词的组合 SQL 断言
5. 成本验证 (`test_cost__*`, 语句记录器见 README): 注册 k 个过滤器前后同一查询的 ledger.count **不变** (过滤器只改 WHERE 形态不改语句数); 注销后语句形态与基线逐字一致

## 非目标

- 一期不做写侧守卫泛化
- 不做 per-query 动态启用/禁用单条过滤器 (粒度到"全部"即可)
- 不引入 SQLAlchemy `with_polymorphic` / 多态加载的复杂交互 (如遇阻塞则记录并降级为文档警告)
