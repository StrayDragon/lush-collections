# 07 — 幂等写 (Upsert / get_or_create)

> 状态: **提案 (未实现)**
> 影响包: `lush-sqlalchemyx` (ORM 路径 MVP); Dynamic 变体二期
> 关联现状: `cu_row_data` 复用; 测试矩阵含 `mysql:5.7` + `mysql:8.0.40` + SQLite, 方言语义必须对齐
> 镜像约定: 文中示例为 async 形态; sync 镜像方法同步提供, 方法名与语义一致 (README 通用约束).

## 背景与动机

三类高频场景需要"存在即更新 / 不存在即插入":

- **统计宽表**: 每日按 `(user_id, stat_date)` 粒度累加/覆盖
- **外部同步幂等落库**: 重跑不产生重复行
- **去重字典** (`get_or_create`): 标签、类目等唯一名资源

现状只能手写 dialect 特定语句, 且 MySQL 的 rowcount 陷阱、5.7/8.0 语法差异、
SQLite 测试路径的语义对齐全靠业务方自己踩.

## 假想使用示例

### upsert_batch

```python
class UserStatCU(BaseCU[UserStatTable]):
    user_id: int
    stat_date: date          # 与 user_id 组成唯一键
    login_count: int = 0
    last_seen_at: datetime | None = None

# 形态 1: 字符串 — 快捷; 调用瞬间即时校验 (未知列名 ValueError 含可选列表)
await UserStatDAL.upsert_batch(session, cus, conflict_cols=("user_id", "stat_date"))

# 形态 2: ORM 列属性 — pyright 静态检查, IDE rename 自动跟随 (推荐, 同 doc 02 选择器模式)
await UserStatDAL.upsert_batch(session, cus,
    conflict_cols=(UserStatTable.user_id, UserStatTable.stat_date))
```

生成的 SQL (MySQL):

```sql
INSERT INTO user_stat (user_id, stat_date, login_count, last_seen_at)
VALUES (?, ?, ?, ?), (?, ?, ?, ?)
ON DUPLICATE KEY UPDATE
    login_count = VALUES(login_count),
    last_seen_at = VALUES(last_seen_at)     -- 冲突列本身不出现在 SET 中
```

| 场景 | 行为 |
|------|------|
| 全新行 | INSERT, rowcount 每行 1 |
| 唯一键命中 | UPDATE 非 conflict 列 |
| MySQL rowcount 陷阱 | 命中且值有变化返回 **2**, 无变化返回 **0** — 文档明示, API 只承诺 "已落库", 不承诺具体数值 |

### get_or_create

```python
tag, created = await TagDAL.get_or_create(session, TagCU(name="nlp"), by=("name",))
# created=True:  新建
# created=False: 唯一约束冲突 → 回读既有行 (并发安全)

# by 同样接受 ORM 列属性形态 (防漂移机制与 conflict_cols 一致):
tag, created = await TagDAL.get_or_create(session, TagCU(name="nlp"), by=(TagTable.name,))
```

### 列选择器的防漂移 (conflict_cols / by 共用)

与 [02 投影查询](./02-wide-table-patterns.md) 的多形态选择器同一套约定. 签名为
`Sequence[str | InstrumentedAttribute[Any]]` (联合标注, 各形态返回类型无差异故不拆 overload):

| 形态 | 归一化 | 检查时机 |
|------|--------|----------|
| `str` | 直取列名 | 调用时即时校验 (未知列 ValueError 含可选列表) |
| `InstrumentedAttribute` (ORM 列) | 属性名 → 列名映射 | **静态** (pyright) + IDE rename 自动跟随 |

明确不做: `Fields` 嵌套类、checker 插件 (理由同 doc 02).

## 预期语义与效果

### 方言矩阵 (核心复杂度)

| 后端 | upsert 实现 | 备注 |
|------|------------|------|
| MySQL (5.7 & 8.0) | `ON DUPLICATE KEY UPDATE col=VALUES(col)` | `VALUES()` 在 8.0.20+ deprecated 但全矩阵可用 (见决策 #1) |
| SQLite (测试路径) | `ON CONFLICT(cols) DO UPDATE SET col=excluded.col` | oracle 对比测试断言两方言最终效果等价 |

对比测试的判定标准: 同一组 CU × 同一组 conflict_cols, 两方言执行后 **表终态逐行相等** (不比对 SQL 文本).

### get_or_create 并发语义

```
INSERT (savepoint 内)
 ├─ 成功 → created=True
 └─ IntegrityError → rollback to savepoint → 按 by=(...) SELECT 回读 → created=False
```

- 必须用 `begin_nested` (SAVEPOINT): 让冲突回滚不污染外层事务的已有变更
- 回读不到 (极端: 冲突后又被删) → 抛错而非静默重试, 保持可观测

### dump 策略

upsert_batch 的 MVP 采用 **整行 dump (不用 exclude_unset)**:
executemany 要求各行形状一致; patch 语义与 ON DUPLICATE 天然矛盾.
需要部分列覆盖时显式传完整 CU (见决策 #3).

### 成本速览

| 操作 | IO | 备注 |
|------|-----|------|
| `upsert_batch` | **1 次 executemany 往返** (n 行一批), 与 n 无关的语句数 | MySQL rowcount 语义 (1/2/0) 已在上文声明; 空间 O(n × 列数) |
| `get_or_create` 正常路径 | 1 INSERT (+1 点查刷新) | — |
| `get_or_create` 冲突路径 | SAVEPOINT + 失败 INSERT + ROLLBACK + SELECT ≈ 4 次操作 | **罕见路径才付的成本**; 高冲突率场景说明建模有问题, 文档引导改 upsert |

实现期以上表格翻译为 docstring「成本」段 (格式见 [README](./README.md#api-成本标注与转发约定)).

## 待决策项 (Open Decisions)

| # | 决策点 | 当前倾向 |
|---|--------|----------|
| 1 | MySQL `VALUES()` vs alias 语法 (`AS new ... new.col`) | ~~默认 `VALUES()`~~ → **修订**: 引入 `values_syntax="auto"` 档, 按引擎 `server_version_info ≥ (8,0,20)` 自动选 alias/legacy (详见 [10 R3](./10-mysql-mode-compat.md)); 显式传 `legacy` 可固定旧行为 |
| 2 | `upsert_batch` 行形状 | 整行 dump; 混合形状 (有的字段缺有的缺) 按字段集分组发多条语句 —— 二期再考虑 |
| 3 | 需要条件覆盖 (如仅 `login_count = login_count + VALUES(...)` 累加) | 提供第二形态 `increment_cols=("login_count",)`? 或让用户拿底层语句自拼 | 倾向 MVP 只做覆盖式, 累加需求观察后再定 |
| 4 | `get_or_create` 的 `by` 缺省 | 缺省用 CU 全部必填字段子集推断太隐晦 → **必填参数**, 显式声明查找列 |
| 6 | 列选择器形态 (`conflict_cols` / `by`) | 双形态: str (即时校验兜底) + ORM 列属性 (静态检查); 与 doc 02 投影选择器同一套归一化机制, 不做 Fields 嵌套类/插件 |
| 5 | Dynamic TableRef 变体 | 二期 (Core 层天然可行, 但 conformance/测试预算先花在 ORM 路径) |

## 测试策略

1. oracle 对比测试: MySQL 与 SQLite 终态等价性 (上表判定标准), 覆盖 insert/update/no-op 三分支
2. 选择器: str 与 ORM 属性两形态产出等价语句; 未知列名即时 ValueError 含可选列表
3. rowcount 语义固化测试 (防方言升级漂移)
4. get_or_create 并发: 两连接同时 get_or_create 同名 → 一个 True 一个 False, 无死锁无脏事务
5. savepoint 隔离: 外层事务已有未提交变更时遭遇冲突, 外层变更不受影响
6. matrix: mysql5.7 / 8.0 / sqlite 三环境全绿
7. 成本验证 (`test_cost__*`, 语句记录器见 README):
   - `test_cost__upsert_batch__single_roundtrip`: n ∈ {1, 100, 1000} 行 ledger.count 恒等于 1 (insertmanyvalues 单语句; **实现期须核实各方言 executemany 的事件计数行为**, 若方言拆分则按声明上限断言)
   - `test_cost__get_or_create__conflict_budget`: 冲突路径语句数 ≤ 上限常量 (SAVEPOINT 序列), 正常路径 == 基线

## 非目标

- 不做 PostgreSQL `ON CONFLICT` 方言 (当前库面向 MySQL; 结构上预留)
- 不做 MERGE 语义 (按条件更新的多表同步)
- 不做批量条件 upsert (WHERE 化的 UPDATE 分支选择)
