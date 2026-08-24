# 表设计 Pattern 设计文档索引

> 状态: **全部为提案 (未实现)** — 本目录文档仅做规划与 API 假想演示, 不代表已落地行为.
> 影响包: `lush-sqlalchemyx`, `lush-dal-protocol`

## 文档列表

### 第一批 (已 review 轮次一)

| # | 文档 | Pattern | 优先级 |
|---|------|---------|--------|
| 01 | [extend-table-aggregate-dal](./01-extend-table-aggregate-dal.md) | ExtendTable 聚合编排 (1:1 扩展表组合 DAL) | P1 |
| 02 | [wide-table-patterns](./02-wide-table-patterns.md) | 宽表模式 v2: target 装载表 + 快照冗余表 (Spread 列组 / 投影 project() / 批量装载校验 / 分区快照约定) | P2 |
| 03 | [json-column-mechanism](./03-json-column-mechanism.md) | JSON 列机制盘点 + mixin 泛型自动绑定 (DataJson 为 SSOT; TypeDecorator 已否决) | P3 |
| 04 | [global-query-filters](./04-global-query-filters.md) | 全局查询过滤器泛化 (软删机制归一化) | P4 |

### 第二批 (常用表设计 pattern)

> 编号即批内优先级.

| # | 文档 | Pattern | 一句话 |
|---|------|---------|--------|
| 05 | [filter-model](./05-filter-model.md) | FilterModel 声明式列表查询 | 查询条件的 SSOT 也是 Pydantic 模型, exclude_unset 纪律延伸到查询侧 |
| 06 | [state-machine-column](./06-state-machine-column.md) | 状态机列 | 流转图声明式 + CAS 条件更新 + 流转边绑定 Pydantic 载荷 |
| 07 | [upsert-get-or-create](./07-upsert-get-or-create.md) | 幂等写 | ON DUPLICATE KEY / ON CONFLICT 方言对齐 + savepoint 并发安全的 get_or_create |
| 08 | [tree-adjacency](./08-tree-adjacency.md) | 树形结构 (邻接表) | 平铺行 → 递归 Pydantic 树 DTO, O(n) 组装 + 环防护 |
| 09 | [soft-delete-unique-key](./09-soft-delete-unique-key.md) | 软删 × 唯一键共存 | 「存活=0, 删除=id」约定固化, MySQL 无部分索引下的唯一性方案 |

### 横切关注点

| # | 文档 | 主题 | 一句话 |
|---|------|------|--------|
| 10 | [mysql-mode-compat](./10-mysql-mode-compat.md) | 版本混用与非严格模式坑位 | 库的行为不得依赖服务器 sql_mode 与版本; nullability 守卫 / 启动探针 / upsert 自动档 |
| 11 | [typing-test-rigor](./11-typing-test-rigor.md) | 类型与测试工程规范 (**部分落地**: 标记体系/hypothesis/护栏已实施) | TypeVar 纪律 / Annotated 提取契约 / hypothesis 属性测试 / marker 体系 / DoD 检查单 |

## 术语表 (Glossary)

首次出现时以「中文 (English)」形式标注; 下表是全目录的统一解释.

| 术语 | 英文 | 解释 |
|------|------|------|
| DAL | Data Access Layer | 数据访问层: 把数据库读写封装成可复用方法的对象层, 本仓库的核心产物 |
| ORM | Object-Relational Mapping | 对象关系映射: 把数据库表映射成编程语言里的类与对象 (如 SQLAlchemy 的 Declarative 模型) |
| CU | Create/Update model | 写入模型: 创建或更新数据时携带的字段集合 (Pydantic 模型), 只含"允许被写"的字段 |
| DTO | Data Transfer Object | 读出模型: 查询结果返回给调用方的字段集合, 与表结构对应但面向 API 输出 |
| SSOT | Single Source of Truth | 单一事实源: 同一份信息只在一个地方定义, 其余地方引用它 |
| 原语 | primitive | 库提供的最小可组合构件, 复杂能力由它组装而成 |
| oracle 对比测试 | oracle testing | 用一套独立手写的期望实现来校验被测代码的行为是否一致 (`tests/oracle/` 目录) |
| conformance 测试 | conformance suite | 一致性测试套件: 规定 DAL 必须满足的行为清单, 任何实现都跑同一套测试 |
| CAS | Compare-And-Set | 比较并交换: 用一条带条件的 UPDATE 保证并发下只有一个请求生效 |
| CTE | Common Table Expression | 公用表表达式: SQL 的 `WITH ... RECURSIVE` 递归查询写法 (MySQL 8.0 起支持) |
| N+1 查询 | N+1 query | 查列表后逐条再查关联数据的反模式, 语句数随行数线性膨胀 |
| exclude_unset | — | Pydantic 能区分"没传"和"传了 None"; 本库靠它实现部分更新 (patch) 语义 |
| 心智模型 | mental model | 使用者为了正确使用 API 而在脑中维持的概念图景; API 设计的目标是让它保持简单一致 |
| 语法糖 | syntactic sugar | 不新增能力、只让既有能力更好写的便捷形式 |
| 样板代码 | boilerplate | 因框架要求而不得不重复书写的固定代码 |
| foot-gun | foot-gun | 容易被误用而造成事故的 API 设计 ("对着自己脚开枪") |
| fail-fast | fail-fast | 尽早报错: 在声明/启动阶段就校验并失败, 而不是拖到业务运行中 |
| sql_mode | sql_mode | MySQL 的服务器行为开关集; 是否开启严格模式由它决定 |
| 严格模式 | strict mode | `STRICT_TRANS_TABLES` 开启时非法值直接报错; 关闭则静默降级为默认值/截断 |

## 文档结构约定

每份设计文档包含:

- **背景与动机**: 现状痛点, 引用现有机制
- **假想使用示例**: before (现状写法) → after (提案 API), 全部为**未实现的假想代码**
- **预期语义与效果**: 行为契约表格 (SQL 层面发生什么 / 边界情况如何处理)
- **待决策项 (Open Decisions)**: 开放问题 + 当前倾向
- **测试策略**: 按 BDD/oracle 先行惯例
- **非目标**: 明确不做什么

## 通用约束 (适用于所有 pattern)

- async/sync API 一一镜像, 方法签名与语义一致
- 协议层可表达的抽象下沉 `lush-dal-protocol` (ABC + conformance + InMemory 参考); SQLAlchemy 特定实现在 `lush-sqlalchemyx`
- 行为变更先写 oracle 对比测试 (`tests/oracle/`) 再实现
- 100% branch coverage; 每个语法糖 (syntactic sugar) 都要有测试预算
- 独立 minor 版本发布 + CHANGELOG 条目; 破坏性变更须显式记录

## API 设计与类型纪律 (full typing / 坑点最少化)

所有 pattern 的设计与实现共同遵守:

### 类型系统承诺

| 承诺 | 说明 |
|------|------|
| Python 3.10 下限 | 不用 PEP 695 语法; 泛型用 `TypeVar` (+ `typing_extensions.TypeVar` 的 `default=` 实现部分特化), `Self` 用 `typing_extensions.Self` |
| basedpyright `--level error` 全绿 | 公共 API 签名完整标注; 新增模块不得放宽检查 (沿用 integrations/ 例外惯例需记录理由) |
| 多形态参数的精确标注 | 选择器类参数以联合类型标注 (`str \| InstrumentedAttribute[Any]`), 禁止为省事退化为 `Any`; 仅当不同形态导致**返回类型差异**时才拆 `@overload` |
| 泛型对齐跨层传递 | `find_by(flt: FilterModel[_Table])` 式签名让"过滤模型绑错表"在静态期暴露 |
| 静态表达不了的地方诚实声明 | 如 `project()` 返回静态只能是 `type[BaseModel]`; 此时文档明示局限并给出完全类型的替代路径 (手写子集模型)。全部限制集中登记于 [11 类型学限制登记表](./11-typing-test-rigor.md#7-类型学限制登记表-静态到不了的地方汇总) |

> 泛型纪律、Annotated 提取契约、属性测试等工程细则见 [11 — 类型与测试工程规范](./11-typing-test-rigor.md)。

### 坑点最少化三原则

1. **类创建期 fail-fast**: 一切声明式配置 (cu_config / transitions / Spread 注解 / FilterModel 后缀 /
   选择器合法性) 在类体定义时校验 —— 错误暴露于 import/测试收集/CI, 绝不深入请求处理链路
2. **拒绝歧义优于猜测**: 语义有二义性的输入直接抛错 (空 `__in`、Optional 组折叠、重名字段路由…),
   不提供"猜一个合理行为"的默认值
3. **字符串字面量 API 分层防漂移** (02/07 已确立的模式): 即时校验含 did-you-mean 兜底一切形态;
   能路由到既有类型对象 (ORM 列属性 / 组类) 的选择器优先提供静态形态; 文档约定模块级常量前移错误时点

### 低破坏性升级阶梯 (用户明确要求的兼容原则)

> 依据根 AGENTS.md 升级策略的例外条款「除非用户明确要求」—— 本设计集经用户确认遵循低破坏性升级.

**行为语义的变更** (区别于纯新增 API 与内部重构) 一律走三级台阶, 禁止一步到位:

| 阶梯 | 动作 | 用户侧感受 |
|------|------|-----------|
| L1 加选 | 新行为以**显式新参数/新枚举值**提供, 默认值保持旧语义 | 零影响; 新行为 opt-in |
| L2 弃用警告 | 旧默认路径触发新行为的适用条件时发 `DeprecationWarning` (结构化、可静音), 行为不变 | 运行可见但不中断 |
| L3 默认翻转 | 仅在约定的 major 边界 (或用户逐案确认) 执行; CHANGELOG 破坏性条目 + 迁移示例 | 显式升级动作 |

配套规则:
- **编译期破坏** (签名变化导致类型报错) 可走仓库常规一步到位 —— 用户在 CI 即可发现;
- **运行期行为翻转** (如静默成功变抛错) 必须走阶梯 —— 它破坏的是部署而非编译;
- 每级台阶之间至少间隔一个 minor 观察期; L2 的警告必须含迁移指引文本;
- 移除已弃用公共 API 前须单独征求用户确认 (与发版门禁同级别的谨慎).

### 测试与类型的关系

- **类型到不了的地方, 测试必须到**: 动态生成模型的运行时契约 (projected fields / 载荷边绑定)
  以固化测试描述, 防止行为漂移
- conformance 套件同时是类型的运行时镜像: ABC 签名变更必须同步套件 (既有守则), 新 pattern 的
  InMemory 参考实现先行证明套件自身正确

## API 成本标注与转发约定

### docstring 成本标注规范

**强制范围**: 满足任一条件的公共 API 必须在 docstring 中带「成本」段 ——
(a) 产生多于 1 条 SQL 语句; (b) 成本随数据规模/结构变化 (页大小、树深、批量行数、JSON 体积);
(c) 有锁或长事务影响. 其余 API 可省略 (默认即单语句、O(输入)).

统一模板 (四个维度, 变量必须显式命名):

```python
def list_full_by(session, where=None, *, skip=0, limit=20) -> list[FullDTO]:
    """分页聚合查询主表+扩展表.

    ...
    成本:
        IO: 恒定 2 条语句 (主表分页查询 + 页内 ids IN 批查), 与页大小无关
        时间: O(limit × 列数) 反序列化
        空间: O(limit) 个 FullDTO 实例
        锁/事务: 一致性读, 无额外锁
    """
```

- 复杂度以**网络往返数、语句数、行数、列数**表达, 不用抽象大 O 糊弄 IO 事实
- 失败路径成本不同时单独说明 (如状态机冲突补点查)
- 设计文档阶段先以「成本速览」表格呈现, 实现期翻译为上述 docstring 格式

### 转发 API (固定参数的薄封装) 准入规则

**定义**: 对既有 API 固定部分参数或组合固定调用序列的封装, **零新增语义**.
仓库先例: `ret_dto_after_create` ≡ 固定 `need_refresh=True` 的 `create`.

准入条件 (满足其一):
1. 同一调用形态在下游出现 ≥2 处真实重复 (样板代码负担 (boilerplate));
2. 泛型 API 的默认参数在某场景下**次优或有坑**, 需要一个把安全参数固定的变体
   (如批量装载场景需要固定的「salvage 校验 → 分区删除 → 插入」序列).

要求:
- 转发 API 的 docstring 必须**回链被转发者**并声明成本继承关系 ("成本同 X, 差异仅 Y");
- 不允许转发 API 与原 API 语义悄悄分叉 —— 行为差异必须体现为原 API 的新选项;
- 反例守则: 若发现自己在转发层里写分支逻辑, 说明它该是原 API 的选项而非转发 API.

### 成本病态场景的处理义务

泛型 API 在特定数据形态下成本劣化时, 必须**二选一**并在文档标注:
- 提供**缓解选项** (keyword-only, 如 `max_rows` 护栏、`on_error=` 模式切换);
- 或提供**固定安全参数的转发变体** (如 `refresh_partition` 固化校验+删+插序列).
不允许只在小字里提醒用户自行规避.

### 成本的可验证性 (成本即契约)

**原则: 写进 docstring 的每一条成本声明都必须有对应的机器验证; 无法验证的声明
要么补验证手段, 要么从 docstring 降级为普通注释.**

CI **禁止墙钟/内存断言** (flaky 且环境敏感), 全部使用结构代理:

| 声明类型 | 验证手段 | 示例断言 |
|----------|---------|----------|
| 语句数 (精确/上限) | SQL 语句记录器 (Statement Ledger) 计数 fixture | `ledger.count == 2` |
| "排除 N+1" / O(1) 语句 | **规模不变性**: 多个数据规模点下语句数恒等 | n ∈ {1, 50, 200} 时 `count` 均为 2 |
| 单事务语义 | 失败注入 → 整体回滚断言 | DELETE 后 INSERT 失败 → 表内无残留行 |
| 锁影响 | 复用现有 FOR UPDATE / 重试 oracle 手段 | 并发流转竞争测试 (06) |
| 方言差异 | mysql matrix (既有) | upsert 终态等价 (07) |

#### SQL 语句记录器 (Statement Ledger) 基建 (实现于 `lush_sqlalchemyx.testing`, 与 `lush_dal_protocol.testing` 对称)

```python
# 假想形态 — 实现细节实现期定, 契约如下:
ledger = SQLLedger.bind(session_or_engine)   # 挂 before_cursor_execute 事件;
ledger.reset()                               # async/sync 双镜像 (事件在底层同步 Engine 上,
_ = await dal.list_full_by(...)              #  async 会话同样生效)
assert ledger.count == 2                     # 精确计数
assert ledger.statements()[1].startswith("SELECT")  # 形态抽查 (参数已归一化剔除)
```

- 归一化规则: 剔除绑定参数、压缩空白 —— 使 IN 列表大小不影响可比性
- async/sync API 一一镜像 (镜像纪律延伸到测试基建本身)

#### 测试命名与登记约定

- 成本测试统一命名 `test_cost__<api名>__<声明要点>` (如
  `test_cost__list_full_by__statements_const_2`), 打 `@pytest.mark.cost`
- **存在性对应关系**: 公共方法 docstring 含「成本」段 ⇔ 存在同源 cost 测试
- P0: 约定 + 语句记录器 fixture + 各 pattern 的规模不变性测试随实现落地
- P1 (可选工具): `scripts/check_cost_tests.py` 解析源码成本段, 校验测试登记的存在性
  (防文档与测试漂移; 只查存在性不解析数值, 保持简单)

#### 明确不可 CI 验证的声明

墙钟延迟、精确内存占用 **不得写成可验证语气**; docstring 中只允许量级描述
("毫秒级"、"与页大小线性"), 且其定性结论必须能被上表某个结构代理佐证.

## 里程碑切片 (建议)

| 批次 | 内容 | 依赖 |
|------|------|------|
| 第一批 M1 | 01 ExtendTable 聚合 DAL (protocol 编排 ABC → sqlalchemyx 绑定) | 无 |
| 第一批 M2 | 02 宽表模式: Spread 列组 + project() 投影 + validate_rows 装载校验 + refresh_partition | 07 的 upsert_batch 先行 (装载落库复用) |
| 第一批 M3 | 03 E1 泛型自动绑定 + 配方文档 | 无 |
| 第一批 M4 | 04 过滤器注册表重构 (软删行为零变化) → 租户示例 | 建议最后 (纯重构) |
| 第二批 M5 | 05 FilterModel | 无 |
| 第二批 M6 | 06 状态机列 | 无 |
| 第二批 M7 | 07 Upsert/get_or_create (oracle 需跑 mysql matrix) | 无 |
| 第二批 M8 | 08 树形结构 | 无 |
| 第二批 M9 | 09 SoftDeleteUniqueMixin | 建议在 04 之后 (确认过滤谓词兼容) |
| 横切 M10 | 10 R1 nullability 守卫 (**L1 加选引入**: 新枚举 `allow_guarded`, `allow` 冻结不翻转) + R2 探针 | 无 |
| 横切 M11 | 10 R3 upsert 语法定义档 | 依赖 M7 落地 |
| 横切 L2/L3 观察项 | `allow` 弃用警告与远期语义合并 —— 仅 major 边界或用户逐案确认 | M10 后至少一个 minor 观察期 |

## 待办清单 (Backlog)

未立项但有记录价值的需求, 有真实场景时再开设计文档:

| Pattern | 一句话 | 状态 |
|---------|--------|------|
| TimestampMixin 审计列 | `create_datetime`/`update_datetime` 显式 opt-in (审计自动注入移除后的标准替代), server_default + onupdate | 低成本, 可随手并入任一批 |
| 历史影子表 | 主表 update/delete 前 before_flush 自动抄送同构 `_history` 表; 同一 DTO 校验两表 | 中等成本, 待真实需求 |
| 业务单据号 | 单据号生成 (前缀+日期+序号), 依赖 Redis/序列表基础设施 | 出范围 (跨 lush-redisx), 仅记录 |
| 复合主键 / UUID 主键的分页 cursor 全链路 | 原 extend-table ISSUE 后置项: cursor 编解码、`_pk_attr` 类型化、TableRef 泛型联动 | 待真实需求 |
| 多态关联 | `attachable_type/id` ↔ Pydantic 判别联合映射 | 不建议做 (多态外键本身是反模式) |
