# 06 — 状态机列 (StateMachine 列 + 流转级载荷)

> 状态: **提案 (未实现)**
> 影响包: `lush-sqlalchemyx` (mixin + DAL 方法); 错误类型可能下沉 `lush-dal-protocol.errors`
> 关联现状: 乐观锁 (`update_only_set_with_optimistic_lock`) 已有 CAS 精神; 本 pattern 把它带到状态列场景
> 镜像约定: 文中示例为 async 形态; sync 镜像方法同步提供, 方法名与语义一致 (README 通用约束).

## 背景与动机

订单状态、任务状态、审批流 —— 几乎所有业务主表都有状态列. 现状写法的三重问题:

```python
# ── 现状: 先查再改 ──────────────────────────────────
order = await session.get(OrderTable, oid, with_for_update=True)   # 锁窗口大
if order.status != OrderStatus.created:                            # 校验散落业务层
    raise RuntimeError("非法流转")
order.status = OrderStatus.paid
order.pay_no = pay_no                                              # 载荷字段手工赋值
# 并发窗口: 若不用 FOR UPDATE, 两路请求可同时通过校验 (双扣/双发货)
```

- **并发安全**依赖 SELECT ... FOR UPDATE 的锁窗口, 或干脆裸奔
- **合法流转图**只存在于文档/仅存在于口头约定, 代码无法静态校验
- **每条流转的必填载荷** (支付需要 pay_no, 关闭需要 reason) 无类型约束

目标: 流转图声明式定义 + **CAS 条件更新**保证原子性 + 每条流转边绑定 Pydantic 载荷 schema.

## 假想使用示例

### 定义 (一次)

```python
from lush_sqlalchemyx.base.dal import StateMachineMixin   # 假想

class OrderStatus(StrEnum):
    created = "created"
    paid = "paid"
    shipped = "shipped"
    closed = "closed"

TRANSITIONS = {
    OrderStatus.created: frozenset({OrderStatus.paid, OrderStatus.closed}),
    OrderStatus.paid: frozenset({OrderStatus.shipped}),
    OrderStatus.shipped: frozenset(),
    OrderStatus.closed: frozenset(),
}

PAYLOADS = {
    (OrderStatus.created, OrderStatus.paid): PaidCU,     # pay_no: str 必填
    (OrderStatus.created, OrderStatus.closed): CloseCU,  # reason: str 必填
}                                                        # 边为键: 同目标不同来源可带不同载荷

class OrderTable(Base, StateMachineMixin[OrderStatus, PaidCU | CloseCU]):
    """泛型双参数: 状态枚举 + 全部流转载荷 CU 的联合 — transition_by_id 的 cu 参数由此获得静态类型"""
    __tablename__ = "order"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    amount: Mapped[int]
    status: Mapped[str] = mapped_column(sa.String(16), default=OrderStatus.created.value)
    paid_no: Mapped[str | None] = mapped_column(sa.String(64))

    __status_enum__: ClassVar[type[OrderStatus]] = OrderStatus
    __transitions__: ClassVar[Mapping[OrderStatus, frozenset[OrderStatus]]] = TRANSITIONS
    __transition_payloads__: ClassVar[Mapping[tuple[OrderStatus, OrderStatus], type[PaidCU] | type[CloseCU]]] = PAYLOADS
    # 可选: status_changed_at: Mapped[datetime | None] — 声明即自动维护
```

```python
# cu 参数类型 = 泛型第二参的联合; 传未声明的 CU 静态期报错;
# 「这条边该绑哪个 CU」由运行期查 PAYLOADS 收窄 (静态无法按 target 精确到单个 — checker 插件才可, 不做)
dto = await OrderDAL.transition_by_id(session, oid, target=OrderStatus.paid, cu=PaidCU(pay_no="x"))
```

### 使用与效果

```python
# 合法流转: 一条 CAS UPDATE 完成
dto = await OrderDAL.transition_by_id(session, oid,
    target=OrderStatus.paid, cu=PaidCU(pay_no="pay_001"))
```

生成的 SQL (核心效果):

```sql
UPDATE "order"
SET status='paid', paid_no='pay_001', status_changed_at='...'
WHERE id=? AND status IN ('created')      -- ← 原子性来源: 只从声明的来源态流转
```

| 场景 | 行为 |
|------|------|
| 合法且无竞争 | rowcount=1 → 返回刷新后的 DTO |
| 合法但已被并发流转走 | rowcount=0 → 补一次点查读当前态 → 抛 `StatusTransitionError` (携带 `current_status` 属性) |
| 目标态无入边 (如 shipped→paid) | 类创建期已校验流转图; 运行期传非法枚举值在 SQL 前 `ValueError` |
| 载荷缺失/类型错 (`cu=PaidCU()` 缺 pay_no) | Pydantic `ValidationError`, 未触达 DB |
| 该边未声明载荷却传了 `cu` | `TypeError` (防止载荷静默丢弃) |
| 行不存在 | 与现有 DAL 一致返回 `None` 或抛错 (见决策 #5) |

## 预期语义与效果

- **类创建期静态校验**: `__transitions__` 的键值都必须是 `__status_enum__` 成员;
  自环 (A→A) 默认拒绝; 不可达状态 (无入边且非初始态) 给 warning
- **CAS 是唯一并发防线**: 不加 FOR UPDATE, 冲突表现为 rowcount=0;
  失败路径才补点查用于错误信息 —— 正常路径单条 UPDATE
- **走标准写入通道**: 经 session.execute 的 Core UPDATE, 软删过滤/只读守卫等既有钩子照常生效
- **实体缓存**: 更新后 expire 相关实体, 避免 identity map 旧状态泄漏
- **成本** (实现期入 docstring): 正常路径 = 1 条 UPDATE (+1 点查刷新返回 DTO);
  冲突失败路径额外 +1 点查 (仅用于错误信息, 不重试) —— IO 恒定与流转边数无关;
  类创建期校验 O(边数), 一次性的

## 待决策项 (Open Decisions)

| # | 决策点 | 当前倾向 |
|---|--------|----------|
| 1 | 状态存储类型 | **str 后备** (`String(n)` + StrEnum): 免 ALTER、可读、跨库一致; native ENUM / smallint 编码作为可选 config. 理由: MySQL 改枚举值需 ALTER 的运维痛感 |
| 2 | 载荷键粒度 | `(source, target)` 边级绑定; 同目标不同来源的载荷往往确实不同 |
| 3 | 错误类型 | 新增 `StatusTransitionError(ValueError)` 带 `current_status`; 不复用 `DBRetryableError` (业务冲突非基础设施重试语义) |
| 4 | 多来源入边 (`IN ('a','b')`) | 支持; 声明即语义 |
| 5 | 行不存在的行为 | 返回 `None` (与 `update_only_set_by_id` 对齐) |
| 6 | 流转历史 sidecar | 不进本 pattern, 归 [backlog 历史影子表](./README.md#待办清单-backlog) |
| 7 | 载荷的静态类型精度 | 泛型第二参 = 全部载荷 CU 的**联合**, `cu:` 参数静态查"是否声明过"; 按边收窄到单个 CU 只能靠运行期 (checker 插件才可, 不做) — docstring 明示该边界 |
| 8 | 状态在模型层的类型呈现 | 表列保持 `Mapped[str]`; **CU/DTO 字段声明为 `OrderStatus` 枚举**, 经 field_validator 与 str 列互转 —— 调用方全程拿枚举, 库中脏状态在读路径即 ValidationError (fail-fast 延伸到读侧); FilterModel 过滤场景仍按底层 str 比较 |

## 测试策略

1. oracle 对比测试: 手写 CAS UPDATE 与 `transition_by_id` 生成的语句逐字对齐
2. 竞争模拟: 事务 A 持有后人工改库, 断言 B 收到 `StatusTransitionError` 且信息含当前态
3. 类创建期错误矩阵: 非法成员/自环/不可达 warning/载荷边未声明; 流转图可达闭包性质测试归入 [11 属性测试](./11-typing-test-rigor.md)
4. 载荷校验时序: ValidationError 必须先于任何 SQL (用 SQL 计数断言)
5. 与软删组合: 软删行不可流转 (WHERE 自动带上过滤)
6. 成本验证 (`test_cost__*`, 语句记录器见 README): 正常路径 ledger.count == 2 (UPDATE + 刷新点查)、冲突路径 == 3 (额外恰好 1 次当前态点查, 不重试) —— 失败路径成本声明的机器验证

## 非目标

- 不做工作流引擎 (多分支编排/定时器/人审节点)
- 不做分布式 Saga / 补偿
- 不自动建流转历史表
