# 10 — MySQL 版本混用与非严格模式坑位分析 (横切关注点)

> 状态: **提案 (未实现)** — 本文档是横切所有 pattern 的兼容性分析, 不是独立功能
> 影响包: `lush-sqlalchemyx` (`_common.py` NonePolicy 增强 / manager 探针 / 测试基建)
> 现状锚点: 测试矩阵已含 `mysql:5.7` + `mysql:8.0.40-debian`; AGENTS.md 已注明"覆盖非严格 zero-date 与严格模式"
> 关联: [07 upsert](./07-upsert-get-or-create.md) 决策 #1 / [08 树形](./08-tree-adjacency.md) 决策 #2 / [09 软删唯一键](./09-soft-delete-unique-key.md)

## 背景: 两类真实的混用环境

1. **版本混用**: 5.7 与 8.x 并存 (主从不同版本、多业务线渐进升级、云厂商托管版差异)
2. **模式混用**: 运维为兼容遗留数据剥离严格模式 (`SET sql_mode=''` 或缺 `STRICT_TRANS_TABLES`),
   开发/测试连的是默认严格实例 —— **同一份代码两种行为**

设计立场: **库的行为不得依赖服务器 sql_mode 与版本**.
依赖了, 就等于把生产配置变成隐式测试矩阵成员.

## 坑位清单

| # | 坑点 | 严格模式行为 | 非严格行为 | 波及面 |
|---|------|-------------|-----------|--------|
| P1 | NOT NULL 列被写 NULL (`none_policy="allow"` 的正常路径!) | 报错 1048 | **静默写隐式默认值**: `''` / `0` / `'0000-00-00'` | 现有 `update_only_set_by_id` / 全部 update 路径 |
| P2 | 字符串超长 | 报错 1406 | 静默截断 | 所有 str 列写入; CU 若无 `max_length` 校验则库层无防线 |
| P3 | 数值越界 | 报错 | 钳到类型边界 (如 TINYINT 256→127) | status 列类小整数 |
| P4 | 零日期读写 | `NO_ZERO_DATE` 下拒写; 遗留数据读取时驱动抛 `ValueError` | 可写入 | 遗留表接入 / Dynamic 路径裸读 |
| P5 | 递归 CTE | 5.7 无 | — | 08 树形 (已规避) |
| P6 | upsert 语法代际 | 5.7 只支持 `VALUES()` | 8.0.20+ 对 `VALUES()` 发 deprecation warning | 07 (决策 #1 已选 VALUES(), 代价是 8.0 告警噪音) |
| P7 | 默认 collation 代际 | utf8mb4_general_ci | utf8mb4_0900_ai_ci (**重音不敏感**: `café`=`cafe`) | 09 唯一键冲突语义; 跨版本主从一致性 |
| P8 | 隐式 GROUP BY 排序移除 | — | 8.0 起 | 分页/列表 (已强制显式 ORDER BY, 天然免疫) |

## 库级响应 (四道防线)

### R1: nullability 感知的 NonePolicy 守卫 (对 P1 — 按 [低破坏性升级阶梯](./README.md#低破坏性升级阶梯-用户明确要求的兼容原则) 引入)

**原则: 把"服务器模式下才爆的错"变成"任何模式下都一致的库错误" —— 但引入方式走阶梯, 默认零破坏.**

```python
# ── L1 (加选): 新枚举值, "allow" 语义原样冻结 ──────────────
await UserDAL.update_only_set_by_id(session, uid, cu, none_policy="allow")
# 行为与历史版本完全一致 (服务器模式决定结果), 升级零风险

# 新推荐值: 目标列 NOT NULL 时任何模式都抛 TypeError (消息含迁移指引)
await UserDAL.update_only_set_by_id(session, uid, cu, none_policy="allow_guarded")
# → TypeError("字段 'nickname' 映射列 NOT NULL: 非严格模式下会静默写入隐式默认值;
#    请改用 ignore / forbid, 或调整列定义")

# ── L2 (弃用警告): "allow" 命中 NOT NULL 列时 ────────────────
#   非严格会话: 行为不变 (仍写隐式默认值) 但发结构化 DeprecationWarning, 含迁移指引;
#   严格会话: 无需警告 (服务器本就报 1048)
# ── L3 (远期): 仅约定的 major 边界讨论是否让 "allow" 合并 guarded 语义 ──
```

实现基座: DAL 类创建期已做 `validate_orm_dal_pk_config`, 同一时机经 `sa.inspect` 缓存
`_nullable_columns: frozenset[str]` 即可支撑守卫判定.

- 为什么不在第一版就直接翻转默认行为: 它翻转的是**运行期行为** (静默成功 → 抛错),
  破坏的是部署而非编译 —— 按阶梯原则必须给存量非严格部署观察期
- 成本: 每字段一次 frozenset 查询, O(1); 语句记录器验证语句数不变
- 存量用户的升级路径: 启动探针 (R2) 发现非严格 → grep 调用点换 `allow_guarded` → 完成,
  全程无强制

### R2: 启动期模式/版本探针 (对 P1/P4/P6, 检测层)

```python
mgr = MySQLManager(...)          # 连接建立后一次性:
mgr.server_version_info          # (8, 0, 40) — 供 R3 自动档
mgr.is_strict_mode               # bool, 来自 @@session.sql_mode 解析
# 配置项: on_non_strict_mode = "warn" (默认, 结构化日志) | "raise" | "ignore"
```

- 定位: 运维可见性 —— 长连接池里的 warning 没人看, 但启动日志的 WARNING 会被接住
- Flask/FastAPI 集成的 lifespan 处天然是它的调用点 (与 `setup_dal_hooks` 同期)

### R3: upsert 语法的版本自动档 (对 P6, 修订 07 决策 #1)

```python
# upsert_batch 增加 keyword-only:
await dal.upsert_batch(session, cus, conflict_cols=(...),
                       values_syntax="auto")   # auto(默认) | legacy | alias
# auto: 按 mgr.server_version_info ≥ (8,0,20) 选 alias, 否则 legacy VALUES()
```

比原决策更进一步: 原"全矩阵统一 VALUES()"在 8.0.20+ 持续制造告警噪音;
auto 档让两个代际各自使用原生最优语法, oracle 终态等价测试判定标准不变.

### R4: 读侧脏数据的唯一容忍边界 = 显式装载边界 (对 P4, 原则声明)

零日期/截断字符串等遗留脏数据的**唯一**官方入口是 [02 的 `validate_rows(salvage)`](./02-wide-table-patterns.md)
—— 它逐行收集 ValidationError 并上报, 正好兜住驱动层抛出的解析失败.
DAL 核心读路径保持 strict-fail, **库内不做任何静默清洗**.

### R5: collation/索引长度咨询 (对 P7, 文档咨询层)

- 09 的 `(name, is_delete)` 唯一键: 文档标注 8.0 `*_ai_ci` 的重音折叠会让"业务上不同"的名字撞键;
  建表 DDL 显式指定 collation 的建议写入 mixin docstring
- `shortcuts/meta.py` 出 DDL 时附注目标代际差异 (MVP 仅注释, 不做字节预算工具)

## 测试策略 (mode × version 矩阵)

复用现有 mysql matrix, 新增 **mode 参数化 fixture** (仅 compat 标记子集跑双模式, 控制 CI 预算):

```python
@pytest.fixture(params=["strict", "non_strict"])
def mysql_session(request, ...):
    ...  # SET SESSION sql_mode='' 模拟非严格 (与生产剥离方式一致)
```

- `test_compat__null_allow_guarded__raises_both_modes`: 双模式下 guarded 策略对 NOT NULL 列均抛 TypeError
- `test_compat__allow_legacy__frozen_semantics`: **allow 语义冻结测试** —— 非严格下写隐式默认值 (行为与历史版本一致) 且触发 DeprecationWarning; 严格下 1048 原样穿透 (库不拦截)
- `test_compat__probe__detects_stripped_mode`: 会话剥离严格模式后 `is_strict_mode is False`
- `test_cost__upsert__syntax_auto_by_version`: 按 `server_version_info` 断言生成语句形态 (ledger 文本抽查)
- 成本回归: R1 守卫不改变各 API 语句数 (语句记录器计数与既有 `test_cost__*` 重合即覆盖)
- SQLite 路径不受 mode 影响 (Python 类型即最严模式), 相关测试标记 mysql-only

## 待决策项 (Open Decisions)

| # | 决策点 | 当前倾向 |
|---|--------|----------|
| 1 | R1 守卫的引入方式 | **阶梯式, 不做默认翻转**: L1 新增 `allow_guarded` (加选) → L2 `allow` 命中 NOT NULL 且非严格时发 DeprecationWarning (行为不变) → L3 仅 major 边界再议. 依据 README「低破坏性升级阶梯」(用户明确要求的兼容原则) |
| 2 | 新策略命名 | `allow_guarded` — 与 `allow` 并列的新枚举值; **`allow` 永不重定义语义**, 不设 `allow_unchecked` (allow 本身就是未守卫形态) |
| 3 | R2 默认动作 | `warn` (结构化日志). `raise` 会让存量非严格部署无法升级, 违反低破坏性原则 |
| 4 | R3 auto 档的判定源 | 引擎级 `server_version_info` (SQLAlchemy 已缓存, 零额外往返); 不做每语句探测 |
| 5 | P2 截断是否也加库层守卫 | 一期不做 (需长度元数据全量核对, 收益/成本弱于 P1); 由 CU 层 `max_length` 校验承担, 文档引导 |
| 6 | L2 警告的判定来源 | 会话/引擎侧缓存的模式标记 (R2 探针产物), 实现期定挂载点 (manager 缓存或 `session.bind` 属性), 避免每语句查询 `@@sql_mode` |

## 非目标

- 不做 sql_mode 的自动改写 (会话模式是运维主权, 库只探测不建议改)
- 不做通用"非严格模拟器" (不可能穷举服务端行为; 只守卫已知高危交互)
- 不解决跨版本主从复制的数据一致性本身 (R2 只是让它可见)
