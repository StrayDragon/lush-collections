# 08 — 树形结构 (邻接表 ↔ 递归树 DTO)

> 状态: **提案 (未实现)**
> 影响包: `lush-sqlalchemyx` (mixin + DAL 方法); DTO 递归组装原语可能下沉 protocol
> 约束: 测试矩阵含 **mysql:5.7 (不支持 CTE 递归查询)** — 默认实现不得依赖递归 SQL
> 镜像约定: 文中示例为 async 形态; sync 镜像方法同步提供, 方法名与语义一致 (README 通用约束).

## 背景与动机

分类、菜单、组织架构普遍用邻接表 (`parent_id`) 建模. 现状的痛点:

- 组装树靠业务层手写循环 + dict, 每个项目重复一遍; N+1 查询是常见事故
- **环检测**没人做: 脏数据 (`a.parent=b, b.parent=a`) 让组装死循环
- **移动子树**的环检查 (不能移到自己子孙下) 容易漏
- 读侧返回平铺行, 前端要的却是嵌套结构

Pydantic 融合点非常自然: **递归嵌套模型** (`children: list[Self]`) 作为读侧形态.

## 假想使用示例

### 定义

```python
from lush_sqlalchemyx.base.dal import AdjacencyMixin   # 假想

class CategoryTable(Base, AdjacencyMixin):
    __tablename__ = "category"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(64))
    # parent_id 列由 mixin 提供: Mapped[int | None]
    # 可选声明 sort_key 列 → children 按其排序; 可选 depth 列 → 写入时维护

class CategoryDTO(BaseDTO[CategoryCU]):
    id: int
    name: str
    parent_id: int | None

class CategoryNodeDTO(CategoryDTO):
    children: list[Self] = []          # Pydantic v2 递归模型 (typing_extensions.Self, py3.10 兼容)
```

```python
class CategoryDAL(SyncBaseDAL[CategoryTable, CategoryDTO, CategoryCU]):
    _NodeDTO: ClassVar[type[CategoryNodeDTO]] = CategoryNodeDTO
    # 声明后 get_tree / get_subtree 的返回类型静态精确到 list[CategoryNodeDTO]
```

### 使用与效果

```python
# ── 读: 单查询全量行 → 内存 O(n) 组装 → 嵌套树 ──
tree = await CategoryDAL.get_tree(session, root_id=None)   # None = 全部森林
tree[0].children[1].children[0].name

# 效果: SELECT * FROM category (一条); 组装纯内存;
#       发现环 → TreeCorruptionError (携带环路径), 不静默截断不挂死

# 只要某子树:
subtree = await CategoryDAL.get_tree(session, root_id=42)
# 默认策略 load-all-prune: 全量取回后剪出 42 的子树 (5.7 安全, 见决策 #2)

# ── 移动子树 (带环防护) ──
await CategoryDAL.move_subtree(session, node_id=7, new_parent_id=42)
# 校验: 42 的祖先链上出现 7 → ValueError("不能移动到自身子孙之下")
# 通过后单条 UPDATE category SET parent_id=42 WHERE id=7
```

## 预期语义与效果

| 操作 | 实现 | 复杂度 / 风险 |
|------|------|--------------|
| `get_tree(root_id)` | 一条 SELECT 全表(或按需) → id→node dict → 单遍挂接 | O(n); 无 N+1 |
| 环检测 | 组装时访问标记, 二次访问即报错 | 防脏数据死循环 |
| `get_subtree_ids(id)` | 内存遍历 (load-all-prune 下免费) | — |
| `move_subtree` | 先沿 new_parent 向上走祖先链查环, 再单 UPDATE | 祖先链点查若干次 |
| `depth` 维护 | move/insert 时增量更新子孙 depth (可选列) | 子孙批量 UPDATE |
| 排序 | 有 `sort_key` 列则 children 排序, 否则按 id | — |

成本补充 (实现期入 docstring, 格式见 [README](./README.md#api-成本标注与转发约定)):

- `get_tree`: IO 恒定 **1 条全量 SELECT**, 时间/空间 O(n) —— 病态场景 (巨型表) 由
  `max_rows` 护栏兜底, 超限抛错并提示二期 CTE 变体
- `move_subtree`: 祖先链 **O(depth) 次 PK 点查** + 1 条 UPDATE; depth 通常 <10,
  极深树属建模问题 (文档标注)
- depth 维护 (若启用): 子树范围 UPDATE O(子树大小), move 时才发生

### 与既有决策的呼应

- 删除父节点时子的去向 (孤儿策略): 本 mixin **不做隐式处理**, 文档指向与 doc 01 相同的取舍原则
  (孤儿比多删更危险 → 推荐业务层显式级联或拒绝删除有子节点者)
- 只读/软删钩子照常生效 (走标准 session)

## 待决策项 (Open Decisions)

| # | 决策点 | 当前倾向 |
|---|--------|----------|
| 1 | `parent_id` 自引用 FK 是否由 mixin 声明 | **不建 FK**, 仅列 + 索引. 理由: 业务表普遍回避自引用外键的级联耦合; 环防护已在应用层做 |
| 2 | 子树查询默认策略 | **load-all-prune** (矩阵含 5.7 无 CTE); 加 `max_rows` 护栏 (超限抛错提示改用 CTE 变体); MySQL8+ 的递归 CTE 变体二期 opt-in |
| 3 | `move_subtree` 并发 | MVP 接受窄竞态窗口 (校验与 UPDATE 非原子), 文档标注; 严格场景用现有 `get_by_id_for_update` 锁祖先链自行组合 |
| 4 | 树 DTO 由谁声明 | 用户显式写 `children: list[Self]`; DAL 侧以 `_NodeDTO` ClassVar 绑定 → 树 API 返回类型静态精确 (未声明时调用树 API 即 `TypeError`, fail-fast) |
| 5 | 组装函数的类型签名 | 接受任意"含 children 字段的模型"→ 签名用 Protocol (`HasChildren`) 描述而非具体基类; 返回类型与传入 node_dto 绑定 (`type[N] -> list[N]`) |
| 6 | 多棵树并存 (森林) | `root_id=None` 返回 `list[RootNode]`; 单根场景用户取 `[0]` |

## 测试策略

1. oracle 对比测试: 组装结果 vs 手写 dict 循环的输出等价
2. 环注入测试: 手工造两节点互指 → `TreeCorruptionError` 且路径信息正确
3. move 环防护矩阵: 移到自身/直接子女/深层子孙/合法祖先 各态
4. 大表护栏: max_rows 超限报错
5. depth 维护正确性 (若做): 嵌套 5 层移动后各层 depth 断言
6. SQLite 全量 + matrix 抽样 (CTE 变体落地时才涉及 MySQL8 专项)
7. 成本验证 (`test_cost__*`, 语句记录器基建见 README):
   - `test_cost__get_tree__statements_const_1`: n ∈ {10, 500, max_rows 边界} 规模不变性, ledger.count 恒等于 1; 超限抛错路径的语句数实现期定并回写声明
   - `test_cost__move_subtree__depth_plus_one`: 深度 d 的固定夹具下 ledger.count == d + 1 (祖先链点查 + UPDATE)

## 非目标

- 不做 nested sets / materialized path / closure table 等其他树存储模型 (邻接表为主流默认; 其他模型按需另立)
- 不做树的持久化排序拖拽协议 (前端交互层)
- MVP 不做 CTE 深查
