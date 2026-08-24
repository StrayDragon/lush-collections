# 05 — FilterModel (声明式列表查询过滤模型)

> 状态: **提案 (未实现)** — 新 pattern 中优先级最高
> 影响包: `lush-sqlalchemyx` (谓词构建 + `find_by` DAL 方法); 后续可桥接 `lush-fastapix`
> 复用现状: `exclude_unset` 心智模型、`escape_like`、`_pagination.py` 的 offset/cursor 工具
> 镜像约定: 文中示例为 async 形态; sync 镜像方法同步提供, 方法名与语义一致 (README 通用约束).

## 背景与动机

列表页/管理端 API 的最大样板来源是手拼 `where` 列表: 每个可选条件一段
`if req.stage is not None: stmt = stmt.where(...)`. 条件一多, 视图层膨胀且无法静态校验.

目标: **查询条件的 SSOT 也是 Pydantic 模型** —— 与 CU (写侧 SSOT) 完全同构的心智模型,
未设置字段自动跳过, 操作符用后缀约定静态解析, 类创建期即报非法配置.

## 假想使用示例

### 定义

```python
from lush_sqlalchemyx.base.dal import FilterModel   # 假想

class JobFilter(FilterModel[ReportJobTable]):
    """泛型参数绑定表 → 字段名可静态解析到列"""
    stage: str | None = None                     # 默认操作符: eq
    stage__in: frozenset[str] | None = None      # in
    created_at__gte: datetime | None = None      # gte
    created_at__lt: datetime | None = None       # lt
    report_name__like: str | None = None         # like — 自动套 escape_like
```

### 使用

```python
f = JobFilter(stage="init", created_at__gte=yesterday)
# 未设置的字段 (stage__in 等) 不产生任何条件 —— 与 CU patch 同一套纪律

result = await ReportJobDAL.find_by(session, f, offset_pagination=OffsetPagination(skip=0, limit=20))
result.items        # list[DTO]
result.total        # int (count 查询, 与现有分页工具复用)

cur = await ReportJobDAL.find_by(session, f, cursor_pagination=CursorPagination(cursor="...", limit=50))
```

### 效果

| 输入 | 生成的 WHERE 片段 |
|------|------------------|
| `stage="init"` | `stage = 'init'` |
| `stage__in={"a","b"}` | `stage IN ('a','b')` |
| `created_at__gte=X, created_at__lt=Y` | `created_at >= X AND created_at < Y` |
| `report_name__like="%x%"` | `report_name LIKE '%x%'` (用户输入经 escape_like) |
| 全部未设置 | 无额外 WHERE |

## 预期语义与效果

- **类创建期校验**: 字段名去掉后缀后必须在 `_Table` 上存在同名 ORM 属性; 操作符不在支持集内;
  类型与操作符不匹配 (`stage__gte: str`) —— 均 `TypeError`, fail-fast 在 import 时
- **条件生成**: `model_dump()` 中值不为 `None` 的字段才生成谓词 (见决策 #1)
- **find_by 组合**: 过滤谓词 + 现有 `build_offset_stmt` / `build_cursor_stmt`;
  cursor 分页自动附加 PK 排序保证确定性
- **成本** (实现期入 docstring): 谓词生成 O(已设字段数); offset 形态 = **2 条语句**
  (COUNT + SELECT, total 是它的主要额外成本), cursor 形态 = **1 条** —— 大表列表页推荐 cursor,
  该取舍与现有分页工具一致; LIKE 转义 O(输入长度)
- **Dynamic 路径**: `FilterModel` 绑定 TableRef 的变体 (字段名经 resolved_columns 映射), 二期

## 待决策项 (Open Decisions)

| # | 决策点 | 当前倾向 |
|---|--------|----------|
| 1 | 显式传 `None` 语义 | 一律跳过 (不生成谓词). 理由: HTTP query 参数缺省即为 None, "显式 null 过滤" 无真实场景; 需要 IS NULL 时提供 `field__isnull: bool` 显式操作符 |
| 2 | 空集合 `__in=set()` | 抛 `ValueError` (语义歧义: 恒假还是跳过?) |
| 3 | 操作符集合 (MVP) | `eq/ne/in/not_in/gt/gte/lt/lte/like/isnull`; 不含 json/嵌套路径 |
| 4 | 排序白名单 | 独立声明 `__sortable__ = (...,)` + find_by 的 `order_by` 参数校验, 防排序注入 |
| 5 | 放置位置 | sqlalchemyx (ColumnElement 是 SA 概念); 命名约定文档若需跨实现共享再抽 protocol |
| 6 | FastAPI 桥接 | 二期进 lush-fastapix: filter model 直接作为 query params 依赖注入 |
| 7 | 与 DAL 泛型的静态对齐 | `find_by` 签名声明为 `flt: FilterModel[_Table]` — 过滤模型绑错表在**静态期**报错 (而非运行期字段解析失败); FilterModel 本体的字段→列校验仍在类创建期 (import 时点) |

## 测试策略

1. 类创建期错误矩阵: 未知字段 / 未知操作符 / 类型错配 / 空 `__in`
2. 谓词 SQL 断言: 每个操作符 × 设置/跳过/显式 None 三态
3. 与分页组合: offset (含 total) 与 cursor 两形态
4. oracle 对比测试: 手拼 where 与 FilterModel 生成的语句逐字对齐
5. like 注入: `%`/`_` 转义回归
6. 后缀解析器的性质测试 (非法后缀必报错 / 谓词列名恒在表列集内) 归入 [11 属性测试](./11-typing-test-rigor.md)
6. 成本验证 (`test_cost__*`, 语句记录器见 README): offset 形态 ledger.count 恒等于 2 (COUNT+SELECT)、cursor 形态恒等于 1, 规模不变性点 n ∈ {1, 100}; 谓词生成零 SQL (纯内存)

## 非目标

- 不做 JSON 列内部路径过滤、不做全文检索语义
- 不做 join 关联表的跨模型过滤 (保持单表, 关联查询另立)
- MVP 不做 Dynamic TableRef 变体
