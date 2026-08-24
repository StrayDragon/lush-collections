# 02 — 宽表模式 (target 装载表 与 快照冗余表)

> 状态: **提案 (未实现)** — v2 重构: 原「宽表列组」单方案扩展为双场景覆盖
> 影响包: `lush-pydanticx` (批量校验原语, 待定), `lush-dal-protocol` (Spread 原语, 待定), `lush-sqlalchemyx` (投影/分区接线)
> 写侧依赖: 批量装载的落库复用 [07 upsert-get-or-create](./07-upsert-get-or-create.md) 的 `upsert_batch`
> 镜像约定: 文中示例为 async 形态; sync 镜像方法同步提供, 方法名与语义一致 (README 通用约束).

## 两类"宽表", 一套文档

review 澄清结论: "大宽表"在两种语境下出现, 库应分别对待但共享部分能力:

| | **B. target 装载表** (ETL 产出) | **A. 快照冗余表** (业务主表) |
|---|---|---|
| 典型 | DWD 层产出表、报表集市 (如费用周期宽表) | 用户主表 + 统计/偏好快照列 |
| 列来源 | 多个上游源系统按**来源域**合并 (`user_*`, `order_*`, `stat_*`) | 本实体 + 关联实体冗余 |
| 写形态 | **批量装载**: upsert / 分区删插, 幂等优先 | 单行 patch |
| 读形态 | 后台列表/分析: **列子集投影**, 避免百列 SELECT * | 详情整行取回 |

能力矩阵:

| 能力 | B 装载表 | A 冗余表 |
|------|---------|---------|
| Spread 列组组织 | ✓ (来源域分组) | ✓ (主场景, patch 语义) |
| 投影查询 `project()` | ✓ 主场景 | 可用 |
| 批量装载校验 `validate_rows()` | ✓ 主场景 | — |
| 分区/快照约定 | ✓ | 少见 |
| 批量落库 | → 07 `upsert_batch` | — |

---

## 能力 1: Spread 列组 (两场景通用的组织辅助)

扁平列 ↔ 嵌套 Pydantic 模型的双向展开/组装, 物理表保持平铺:

```python
class LoginStats(BaseModel):
    login_count: int = 0
    last_login_at: datetime | None = None

class UserWideDTO(BaseDTO[UserWideCU]):
    id: int
    user_name: str = Field(alias="user_name")
    stats: Annotated[LoginStats, Spread(prefix="st_")]   # 列 st_login_count / st_last_login_at
```

核心机制 (与初版设计一致, 三条规则):

- flatten/unflatten 全程操作 **dict**, 不产生中间模型实例 —— 写路径在 dump 后展开、读路径在 validate 前组装
- Pydantic 的 fields_set 按子模型递归传播 → 未设置的叶子自动缺席, **A 场景的 patch 语义天然保住**
  (`UPDATE ... SET st_login_count=5` 只写已设置叶子)
- 展开规则: 组字段的每个叶子取自身 db 列名 (alias 解析结果) 再叠加组前缀;
  元数据提取契约 (`include_extras=True` 等陷阱) 统一见 [11 §2](./11-typing-test-rigor.md)

对 B 场景的价值: 来源域前缀列组织成嵌套模型后, 投影查询可以按组引用 (见下).

## 能力 2: 投影查询 `project()` (B 主场景)

### 定义侧零成本, 使用侧动态子集 —— 且选择器防漂移

字符串字面量选择器会随字段改名而漂移, 因此 `project()` 接受**多形态选择器**, 分层设防:

```python
# 形态 1: 字符串 — 快捷; 配合「模块级常量」约定, 漂移在 import/CI 时即爆出
ColsListDTO = UserWideDTO.project("id", "user_name", "stats")

# 形态 2: ORM 列属性 / Spread 组类 — 静态检查 + IDE rename 跟随 (推荐)
ColsListDTO = UserWideDTO.project(
    UserWideTable.id,
    UserWideTable.user_name,
    LoginStats,              # 组类整体引用, 展开为该组全部叶子
)

rows, total = await UserWideDAL.find_by(
    session, JobFilter(stat_date=today),
    projection=ColsListDTO,
    offset_pagination=OffsetPagination(skip=0, limit=50),
)
rows[0].stats.login_count    # 嵌套结构保留
rows[0].order_amount         # AttributeError — 子集模型根本没有这个字段

# 任何形态下, 未知选择器都在 project() 调用瞬间报错 (而非查询执行时):
UserWideDTO.project("user_nam")
# ValueError: 未知字段 'user_nam', 可选: id, user_name, stats, order_amount, ...
```

### 选择器归一化与检查时机

| 形态 | 归一化 | 检查时机 |
|------|--------|----------|
| `str` | 直取字段名 | 调用时即时校验 (含 did-you-mean) |
| `InstrumentedAttribute` (ORM 列) | 反查属性名匹配 DTO 字段 (复用 `resolved_columns` 反向机制, 含 Spread 叶子) | **静态** (pyright) + IDE rename 自动跟随 |
| `type[BaseModel]` (Spread 组) | 须为该 DTO 登记过的组注解, 展开叶子 | **静态** (import 存在性) + 调用时归属校验 |

明确拒绝的两个替代方案 (记录理由): 手写 `Fields` 嵌套类 (重复声明本身成为新漂移源);
类型检查器插件合成 `Literal` (维护成本远超收益).

### 效果

| 阶段 | 行为 |
|------|------|
| `project()` | 按 `model_fields` 取子集; Spread 组展开为其叶子; `create_model` 动态生成子模型 (**按字段集 memoize 缓存**, 同一子集不重复建类) |
| SQL | ORM: `load_only` 选列; Core/Dynamic: 只 SELECT 映射后的列 —— 百列表不再拖全列带宽 |
| 校验 | 行字典缺未选列, 但子集模型只声明所选字段 → 单次 `model_validate` 通过 |

### 与 FilterModel 的组合即完整后台列表 API

过滤 (05) + 投影 (本篇) + 分页 (现有工具), 三件套都是声明式 Pydantic 形态.

## 能力 3: 批量装载校验 `validate_rows()` (B 主场景)

ETL 行在写入边界做批量 Pydantic 校验, **逐行收集错误而非一票否决**:

```python
from lush_pydanticx import validate_rows   # 假想位置 (决策 #3)

raw_rows = await fetch_from_upstream()          # list[dict] — 上游抽取的原始行
ok, errors = validate_rows(UserWideDTO, raw_rows)
# ok:     list[UserWideDTO]
# errors: list[RowError(index=3, errors=[...pydantic loc/msg...]), ...]

if errors:
    log_etl_reject(errors)                      # 上报告警/写拒绝清单
await UserWideDAL.upsert_batch(session, ok, conflict_cols=("stat_date", "user_id"))  # 复用 07
```

效果:
- 合法行 salvage 入库, 非法行带 index + 明细上报 —— ETL 不因个别脏行全批失败
- `strict=False` 快速模式 (fail-first, 返回前直接抛聚合 ValidationError) 可选
- 纯 Pydantic 操作, 无 SQLAlchemy 依赖
- **定位 (R4 原则)**: 这是库对遗留脏数据 (零日期/截断字符串等非严格模式产物) 的**唯一官方容忍边界**;
  DAL 核心读路径保持 strict-fail, 库内不做任何静默清洗 (见 [10 R4](./10-mysql-mode-compat.md))

## 能力 4: 分区/快照约定 `PartitionSnapshotMixin` (B 主场景)

按天快照的 target 表惯例固化. **不做魔法默认** (自动"最新分区"过滤隐含数据新鲜度假设,
风险大于收益), 只提供显式原语:

```python
class DailyUserWide(Base, PartitionSnapshotMixin):    # 提供 dt: Mapped[date] 列约定 + 索引
    __tablename__ = "dwd_user_wide"
    ...

# ── 幂等重跑: 单事务内 DELETE 分区 + 校验 + INSERT ──
await DailyUserWideDAL.refresh_partition(
    session, dt=date(2026, 8, 24), cus=cus,
)   # 内部: validate_rows(salvage) → DELETE WHERE dt=:dt → INSERT; 任一步失败整体回滚

# ── 读侧显式指定分区 (与 FilterModel 自然组合) ──
latest = await DailyUserWideDAL.latest_dt(session)               # 辅助查询: MAX(dt)
rows, _ = await DailyUserWideDAL.find_by(
    session, DailyWideFilter(dt__eq=latest),
    projection=ColsListDTO, offset_pagination=...,
)
```

效果: ETL 重跑天然幂等 (同 dt 先删后插); 读方永远显式声明数据版本, 不猜.

---

## 成本速览

| 能力/操作 | IO | 时间 / 空间 |
|-----------|-----|------------|
| Spread flatten/unflatten | 0 (纯内存) | 每行 O(F) dict 操作 (F=叶子总数); 不改变 SQL 形态 |
| `project()` 首次调用 | 0 | create_model 类构建 ~毫秒级; memoize 后 O(1) 查表 —— **模块级常量约定使该成本发生在 import 时** |
| 投影查询 | 与普通查询相同语句数 | 带宽按所省列字节线性下降; `load_only` 无额外往返 |
| `validate_rows()` | 0 (不触库) | O(n × F) 校验; 空间 O(n) 合法行 + O(错误行 × 明细数) |
| `refresh_partition` | DELETE 1 条 + INSERT executemany 1 次, 单事务 | 事务持锁时长 ∝ 行数 (决策 #5 已标注量级边界) |

病态场景义务的落实: `PartitionSnapshotMixin` 的 `dt` 列**默认声明索引**
(`mapped_column(index=True)`), 从结构上消除「无 dt 索引 → DELETE 全表扫 + 大锁范围」的
退化路径; 用户显式关掉时 docstring 必须复述该后果.

---

## 待决策项 (Open Decisions)

| # | 决策点 | 当前倾向 |
|---|--------|----------|
| 1 | `project()` 缓存策略 | 按请求字段集 memoize (类级 LRU); 文档推荐模块级赋值持有引用避免运行期建类 |
| 2 | 投影的实现路径 | ORM 用 `load_only` (identity map 兼容), Core/Dynamic 直接选列; 两者行为对齐由测试保证 |
| 9 | 选择器形态与防漂移 | 多形态归一化: str / ORM 列属性 / Spread 组类; 即时校验兜底 + 静态层覆盖 ORM 路径; 不做 Fields 嵌套类与 checker 插件 |
| 10 | `project()` 返回类型的静态诚实声明 | 签名只能到 `-> type[BaseModel]` (动态建类的字段对 checker 不可见) — docstring 明示此局限; **高频投影场景文档引导手写子集模型** (完全类型化, `find_by(projection=...)` 同样接受), project() 定位为 ad-hoc/低频便利 |
| 3 | `validate_rows()` 放哪 | **lush-pydanticx** (纯 Pydantic, 其他包也能用); sqlalchemyx 只消费其结果 |
| 4 | validate 默认模式 | salvage (收集错误保留合法行) 为默认; `on_error="raise"` 显式切换 |
| 5 | `refresh_partition` 大批量 | MVP 单事务, docstring 标注建议行数量级 (百万级行应走 DB 原生装载, 非库职责) |
| 6 | 最新分区自动过滤 | **不做**. 仅提供 `latest_dt()` 辅助查询, 读方显式组合 FilterModel |
| 7 | Spread Optional 组限制 | 维持 MVP 非 Optional (沿袭原决策 #2) |
| 8 | `dt` 列名 | 约定 `dt` (数仓习惯); mixin 参数可改 |

## 测试策略

1. project(): memoize 命中、组引用展开、ORM load_only 与 Core 选列的 SQL 断言、越权字段 AttributeError
2. 选择器防漂移: 三形态归一化等价性 (同一字段集产出同一子集模型)、未知 str 即时报错含 did-you-mean、ORM 属性→DTO 字段反查 (含 Spread 叶子)、未登记组类归属报错
3. validate_rows(): 混合批次 salvage/raise 两模式、RowError 结构 (index + loc)、空批次边界
4. refresh_partition(): 重跑幂等 (两次执行终态相等)、中途失败回滚 (DELETE 已执行但 INSERT 失败的场景)、与软删/只读钩子共存
5. oracle 对比测试: 手写 load_only/select 列 vs 投影生成的语句逐字对齐
6. matrix: MySQL 抽一处百列表投影场景
7. 成本验证 (`test_cost__*`, 语句记录器基建见 [README](./README.md#成本的可验证性-成本即契约)):
   - `test_cost__project__memoize_identity`: 同字段集两次调用返回**同一个类对象** (memoize 的机器可观测形式)
   - `test_cost__validate_rows__zero_sql`: ledger.count == 0 (纯内存契约)
   - `test_cost__refresh_partition__single_tx_rollback`: 失败注入后分区原数据完整保留
   - `test_cost__dt_column__indexed_by_default`: `sa.inspect` 断言 dt 列索引存在 (结构性病态防护的验证)
8. Spread 往返与 Annotated 提取契约的性质/固化测试归入 [11 属性测试与提取契约](./11-typing-test-rigor.md): `unflatten(flatten(d)) == d` 恒等、patch 字段集保持、`include_extras=True` 剥离陷阱

## 非目标

- 不做 ETL 编排/调度本身 (DataWorks/Airflow 领域), 库只管"落地那一刻"
- 不做多表 JOIN 出宽表的物化过程 (那是 SQL/视图层)
- 不做自动最新分区读、不做分区裁剪下推 (MySQL 分区表的原生 partition 选择语法不在范围)
- Spread 递归嵌套组仍延后 (沿袭原非目标)
