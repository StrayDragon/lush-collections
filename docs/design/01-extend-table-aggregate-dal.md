# 01 — ExtendTable 聚合编排 (1:1 扩展表组合 DAL)

> 状态: **提案 (未实现)** — 前置机制已落地, 本文档只提案"聚合编排"这一层
> 影响包: `lush-dal-protocol` (编排 ABC + conformance), `lush-sqlalchemyx` (SQLAlchemy 绑定)
> 前置: 见下文[现状基线](#现状基线-已落地-原-issue-归档并入) (原根目录 extend-table ISSUE 已归档并入本文)
> 命名候选: `ExtendTableDAL` / `AggregateDAL` / `PairedDAL` (下文暂用 `AsyncExtendTableDAL`, 待定)

## 现状基线 (已落地, 原 ISSUE 归档并入)

> 业务来源: 异步后台任务系统 Producer 侧实践 —— 主表承载通用状态机 + 运行态 JSON (`data_json`),
> 扩展表按类型承载提交参数快照与结构化查询列; 关系为 `extend.id = main.id` (共享主键, 扩展表不自增).

前置 ISSUE (P0 + P0.5) 已交付的能力, 本提案直接复用、不重新设计:

| 能力 | 落地位置 |
|------|----------|
| CU create 时保留共享 PK | `BaseCU.cu_config = EXTEND_TABLE_CU_CONFIG` (`to_orm_exclude=frozenset()`, update 仍排除 PK) |
| 自定义主键名成对配置 | `pk_field_cu_config(pk)` × DAL `_pk_attr`, 类创建期 `validate_orm_dal_pk_config` 一致性校验 |
| Dynamic 显式 PK insert | `DynamicTableConfig(exclude_pk_on_create=False)`; update 路径始终排除 PK |
| "扩展表必须独立 DAL" 约定 | 文档约定: 禁止用主表 DAL 的 create 写扩展行 |
| InMemory 客户端 PK insert | protocol 参考实现 (conformance 支撑) |

原 ISSUE 后置项的去向:

- ~~P1 PairedCreateMixin / P2 JOIN 组装 helper~~ → **即本文档** (JOIN 组装经决策 #5 二期)
- 复合主键 / UUID 分页 cursor 全链路 → 移入 [README 待办清单](./README.md#待办清单-backlog)

## 背景与动机

主表 + 1:1 共享 PK 扩展表已有一等支持, 但只到 **CU 配置层** (`create` 时保留 id).
写路径的三步编排和读路径的两次查询 + 手工拼装仍由业务层重复书写:

```python
# ── 现状: 每个扩展表场景都要手写这套序列 ──────────────────
# 写: 主表 create → 手工回填共享 PK → 扩展表 create (同事务)
main_dto = await ReportJobDAL.ret_dto_after_create(session, ReportJobCU(stage="init"))
await ReportJobExportDAL.ret_dto_after_create(
    session,
    ReportJobExportCU(id=main_dto.id, report_name="x"),   # 手工注入共享 PK
)

# 读: 查两次再拼, 且要处理扩展行不存在
job = await ReportJobDAL.get_by_id(session, job_id)
export = await ReportJobExportDAL.get_by_id(session, job_id)   # 可能 None
full = {...}  # 手工拼装

# 更新: 字段归属全凭开发者记忆, 容易漏掉扩展表那一条
```

目标: 把「共享 PK 的两张表」当作**一个聚合原语**, 编排逻辑收敛到一个组合 DAL.

## 假想使用示例

### 定义侧 (一次)

```python
from lush_sqlalchemyx.base.dal import (
    AsyncBaseDAL, AsyncExtendTableDAL, BaseCU, BaseDTO,
    compose_full_dto,  # 假想: mixin 组合 + 重名字段显式报错
)

# ---- 表 (与现状完全一致, 不新增任何表层概念) ----
class ReportJobTable(Base, FieldMixin):
    __tablename__ = "report_job"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    stage: Mapped[str]

class ReportJobExportTable(Base):
    __tablename__ = "report_job_export"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # 共享主键, 非自增
    report_name: Mapped[str]

# ---- CU / DTO (与现状一致) ----
class ReportJobCU(BaseCU[ReportJobTable]):
    _Table = ReportJobTable
    stage: str

class ReportJobDTO(BaseDTO[ReportJobCU]):
    _CU = ReportJobCU
    id: int
    stage: str

class ReportJobExportCU(BaseCU[ReportJobExportTable]):
    _Table = ReportJobExportTable
    cu_config = EXTEND_TABLE_CU_CONFIG      # create 保留 id, update 排除 id
    id: int
    report_name: str

class ReportJobExportDTO(BaseDTO[ReportJobExportCU]):
    _CU = ReportJobExportCU
    id: int
    report_name: str

# ---- 子 DAL (与现状一致) ----
class ReportJobDAL(AsyncBaseDAL[ReportJobTable, ReportJobDTO, ReportJobCU]):
    _Table = ReportJobTable; _DTO = ReportJobDTO; _CU = ReportJobCU

class ReportJobExportDAL(AsyncBaseDAL[ReportJobExportTable, ReportJobExportDTO, ReportJobExportCU]):
    _Table = ReportJobExportTable; _DTO = ReportJobExportDTO; _CU = ReportJobExportCU

# ---- 新增的全部内容: 一个聚合声明 ----
class ReportJobFullDTO(ReportJobDTO, ReportJobExportDTO): ...
# 或 ReportJobFullDTO = compose_full_dto("ReportJobFullDTO", ReportJobDTO, ReportJobExportDTO)

class ReportJobAggDAL(AsyncExtendTableDAL[
    ReportJobDTO, ReportJobCU, ReportJobExportDTO, ReportJobExportCU,
]):
    _main_dal: ClassVar[type[ReportJobDAL]] = ReportJobDAL
    _ext_dal: ClassVar[type[ReportJobExportDAL]] = ReportJobExportDAL
    _DTO: ClassVar[type[ReportJobFullDTO]] = ReportJobFullDTO     # 合成读模型
    _cascade_delete_ext: ClassVar[bool] = True                    # 默认级联软删扩展表
```

### 使用侧

```python
agg = ReportJobAggDAL  # classmethod 风格, 与现有 DAL 一致

# ── 创建: 子 CU 各自验证, 编排层负责顺序与共享 PK 回填 ──
full = await agg.create_with_ext(
    session,
    main=ReportJobCU(stage="init"),
    ext=ReportJobExportCU(report_name="x"),     # 可选参数
)
full.id            # 1  (来自主表自增)
full.stage         # "init"
full.report_name   # "x"

# 也允许只建主表, 扩展行延迟挂载:
full = await agg.create_with_ext(session, main=ReportJobCU(stage="init"))
# 效果: 只 INSERT report_job; report_job_export 无行

# 后补扩展行:
await agg.attach_ext(session, entity_id=1, ext=ReportJobExportCU(id=1, report_name="x"))

# ── 读: 合成 DTO, 扩展行缺失时 .ext 语义见效果表 ──
full = await agg.get_full_by_id(session, 1)
# 返回 FullDTO; 若扩展行不存在, report_name 相关字段为 None (见"预期语义")

rows = await agg.list_full_by(session, where=[ReportJobTable.stage == "init"], skip=0, limit=20)
# 效果: 先按现有分页语义查主表页, 再对页内 ids 用 batch IN 取扩展行 (2 条 SQL, 不是 N+1)

# ── 更新: 只更新传入的子 CU, 同事务拆两条 UPDATE ──
await agg.update_full_by_id(session, 1, main=ReportJobCU(stage="done"))
# SQL: UPDATE report_job SET stage='done' WHERE id=1        (扩展表不动)

await agg.update_full_by_id(
    session, 1,
    main=ReportJobCU(stage="done"),
    ext=ReportJobExportCU(id=1, report_name="y"),   # id 仅用于满足必填, dump 时排除
)
# SQL: 同一事务内两条 UPDATE

# ── 删除: 默认级联软删扩展行 ──
await agg.delete_full_by_id(session, 1)
# SQL (软删配置时): UPDATE ... SET is_delete=1 WHERE id IN (主表, 扩展表各一条)
```

## 预期语义与效果

| 操作 | SQL / 行为 | 边界情况 |
|------|-----------|----------|
| `create_with_ext(main=..., ext=...)` | 同事务: INSERT 主表 → 取自增 id → 注入 ext CU 的 PK 字段 → INSERT 扩展表 | ext CU 的 PK 字段名经 `resolve_cu_config()` 反推, 不硬编码 `"id"` |
| `create_with_ext(main=...)` | 仅 INSERT 主表 | 不产生孤儿扩展行 |
| `attach_ext(...)` | INSERT 扩展表 (显式 PK); 已存在时抛错还是 upsert? **待决策** | 主表行必须存在, 否则 `ValueError` |
| `get_full_by_id` | 2 次 PK 点查 (非 JOIN) | 扩展行缺失: 返回合成 DTO, 扩展字段为 `None`; 主行缺失: 返回 `None` |
| `list_full_by` | 主表分页 1 条 + 页内 ids `IN` 批查 1 条 | 扩展行部分缺失时逐行降级为 `None` 字段 |
| `update_full_by_id(main=..., ext=...)` | 同事务两条 UPDATE; 各自遵循子 CU 的 `update_exclude` | 只传一个子 CU 时另一张表零写入; rowcount 返回 `(main_n, ext_n)` 或总数 **待决策** |
| `delete_full_by_id` | 级联: 先扩展表后主表 (各自走各自 DAL 的软删/硬删语义) | `_cascade_delete_ext=False` 时只删主表 |

### 成本速览

| 操作 | IO (语句数) | 时间 / 空间 |
|------|------------|-------------|
| `create_with_ext` | 恒定 ≤4 条 (主表 INSERT+刷新, 扩展表 INSERT+刷新), 单事务 | O(两表列数) / O(1) 行 |
| `attach_ext` | 主表存在性点查 1 + 扩展表 INSERT+刷新 | 同上 |
| `get_full_by_id` | **恒定 2 次 PK 点查**, 与列数无关 | O(列数) / O(1) 行 |
| `list_full_by` | **恒定 2 条** (主表分页 + 页内 ids IN 批查) —— 结构上排除 N+1 | O(limit × 两表列数) / O(limit) 个 FullDTO |
| `update_full_by_id` | 只传哪个子 CU 就几条 UPDATE (1 或 2), 同事务 | — |
| `delete_full_by_id` | 级联时 2 条, 否则 1 条 | — |

实现期以上表格翻译为各方法 docstring 的「成本」段 (格式见 [README](./README.md#api-成本标注与转发约定)).

### 合成 DTO 的字段冲突语义

- `compose_full_dto` 工厂在类创建期检查两个子 DTO 的字段交集, 重名即 `TypeError`
- 手写 mixin 组合 (`class Full(A, B)`) 无法拦截 Pydantic MRO 静默遮蔽 → 文档标注推荐工厂形式

### 协议层下沉

编排序列只依赖 ABC 表面 (`ret_dto_after_create` / `get_by_id` / `delete_by_id`),
因此 `lush-dal-protocol` 可提供:

- `AbstractSyncExtendComposer` / `AbstractAsyncExtendComposer`: 泛型编排基类 (session 类型参数化)
- `testing/reference.py` 增加 InMemory 扩展表参考实现对
- `testing/conformance.py` 增加 `Sync/AsyncExtendConformanceTests` mixin

`lush-sqlalchemyx` 的 `Async/SyncExtendTableDAL` 只是薄绑定 (把 `_pk_attr` 校验等 ORM 特性接进来).

## 待决策项 (Open Decisions)

| # | 决策点 | 当前倾向 |
|---|--------|----------|
| 1 | 扁平路由便捷写法 (单个扁平 CU 按子 CU 字段集自动分流) 是否进第一版 | **不进**. 嵌套 kwargs 已够用; 歧义处理值得单独立项 |
| 2 | `attach_ext` 对已存在扩展行的行为 | 抛 `TypeError`(与只读守卫风格一致); upsert 留给 H (Upsert pattern) |
| 3 | `update_full_by_id` 返回值 | 返回小型 NamedTuple `UpdateSplit(main=int, ext=int)` — 信息无损且可解构 |
| 4 | 删除级联默认值 | `True`. 孤儿扩展行比多删一行更危险 |
| 5 | 读路径 JOIN 优化 | 二期. 两次 PK 点查语义更简单且天然处理部分态 |
| 6 | 合成 DTO 的声明形式 × 类型检查 | **手写 mixin 继承为主** (字段静态可见, pyright 可查访问); `compose_full_dto` 工厂仅作运行期冲突校验的补充 (动态建类返回 `type[BaseModel]`, 静态丢字段信息) — 二者可组合: 手写继承 + 基类钩子做冲突断言 |

## 测试策略 (oracle 先行)

1. oracle 层: 复用并扩展现有 `tests/oracle/extend_table.py` (Core 期望语义已就绪), 补聚合级序列 (create→attach→cascade delete)
2. protocol 层: InMemory 参考实现跑新 conformance mixin, 证明套件自身正确
3. sqlalchemyx: SQLite sync 全量 + MySQL matrix 抽样; conformance 双向验证
4. 成本验证 (`test_cost__*`, SQL 语句记录器 (Statement Ledger)见 [README](./README.md#成本的可验证性-成本即契约)):
   - `test_cost__list_full_by__statements_const_2`: n ∈ {1, 50, 200} 规模不变性, ledger.count 恒等于 2
   - `test_cost__get_full_by_id__two_point_selects`: 恒定 2 次 PK 点查
   - `test_cost__create_with_ext__rollback_on_failure`: 扩展表 INSERT 注入失败 → 主表行不残留 (单事务)

## 非目标

- 不引入 SQLAlchemy `relationship()` / 级联插入 (延续前置 ISSUE 的边界)
- 第一版不做扁平路由便捷写法、不做 JOIN 单查询优化
- 不处理多级扩展链 (ext 的 ext) — 有真实需求另开
