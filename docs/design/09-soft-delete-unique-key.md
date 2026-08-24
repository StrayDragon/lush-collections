# 09 — 软删 × 唯一键共存 (SoftDeleteUniqueMixin)

> 状态: **提案 (未实现)**
> 影响包: `lush-sqlalchemyx` (mixin + 文档约定); 无 protocol 改动
> 关联现状: `SoftDeleteTableMixin` (0/1 标记) + 全局过滤谓词 `is_delete == 0`
> 镜像约定: 文中示例为 async 形态; sync 镜像方法同步提供, 方法名与语义一致 (README 通用约束).

## 背景与动机

经典死锁问题: 业务上要求 `name` 唯一, 同时要求软删可恢复/留痕:

```sql
-- 现状 0/1 标记下的两难:
UNIQUE KEY uq_name (name)
-- 行被软删 (is_delete=1) 但行还在 → "张三" 删掉后永远无法重建
```

MySQL **没有部分索引** (`WHERE is_delete=0` 的条件唯一索引是 PG 特性),
无法只对存活行施加唯一性. 业界成熟 workaround 是把删除标记从 0/1 改为
**「存活=0, 删除=自身 id」**, 并把它纳入唯一键:

```sql
is_delete INT NOT NULL DEFAULT 0,
UNIQUE KEY uq_name (name, is_delete)
-- 存活行: is_delete=0 → (name, 0) 唯一 → 活名不重复 ✓
-- 删除行: is_delete=<该行id> → 各删除副本互不相同 → 可无限次删建 ✓
```

这个约定目前靠仅存在于口头约定, 列类型陷阱 (SmallInteger 装不下自增 id)、restore 冲突等细节容易踩.
目标: 固化为 mixin + 约束写法文档.

## 假想使用示例

```python
from lush_sqlalchemyx.base.dal import SoftDeleteUniqueTableMixin   # 假想

class TagTable(Base, SoftDeleteUniqueTableMixin):
    __tablename__ = "tag"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(64))
    # mixin 提供: is_delete: Mapped[int] = Integer default 0   ← 注意不是 SmallInteger
    __table_args__ = (
        sa.UniqueConstraint("name", "is_delete", name="uq_tag_name_alive"),
    )
```

### 使用与效果

```python
await TagDAL.create(session, TagCU(name="nlp"))     # id=1
await TagDAL.delete_by_id(session, 1)               # 软删: SET is_delete=1? NO → SET is_delete=1 不行, SET is_delete=id
# 实际 SQL: UPDATE tag SET is_delete=1 WHERE id=1   ← 错误示范 (现状行为)
# 提案 SQL: UPDATE tag SET is_delete=1 ... 见下表   ← mixin 覆写为 is_delete=1→id

await TagDAL.create(session, TagCU(name="nlp"))     # id=5 → 成功! (name="nlp", is_delete=0) 不与 (nlp, 1) 冲突
await TagDAL.restore_by_id(session, 1)
# 若 (nlp, 0) 已被 id=5 占用 → IntegrityError 原样抛出 (显式冲突, 不静默)
```

## 预期语义与效果

| 操作 | SQL / 行为 |
|------|-----------|
| 软删 | `UPDATE t SET is_delete = <self.id> WHERE id=?` — 覆写 `soft_delete()`, 其余钩子链不变 |
| 存活查询过滤 | `WHERE is_delete = 0` — 与现有全局过滤谓词完全一致 (F 泛化后同样成立) |
| 重建同名 | 不再受历史删除行阻碍 |
| restore | 直接复位 0; 唯一键冲突时 IntegrityError 显式暴露 |
| 列类型 | mixin 自带 `Integer` 列定义 (id 值可能超出 SmallInteger); **与 `FieldIsDeleteSoftDeleteTableMixin` 互斥使用**, 同表混用两个 is_delete 列在类创建期报错 |
| 成本 | 与现有软删路径**完全一致**: 单条 UPDATE, 仅 SET 值不同 (id 而非 1); 无额外查询; 唯一索引写入放大为零 (索引本来就要建) |

## 待决策项 (Open Decisions)

| # | 决策点 | 当前倾向 |
|---|--------|----------|
| 1 | mixin 是否自带列 (像 `FieldIsDeleteSoftDeleteTableMixin`) 还是纯标记 (像 `SoftDeleteTableMixin`) | 自带列. 该模式的列类型/默认值就是约定的一部分, 拆开反而易配错 |
| 2 | 存量表迁移 | 列需 `SMALLINT→INT` 加宽 + 唯一键重建; 属破坏性 DDL, CHANGELOG 记录迁移示例; 不做自动迁移 |
| 3 | 命名 | 列名保持 `is_delete` (语义已变但延续生态习惯) vs 新列名如 `alive_token`. 倾向保持 `is_delete`, docstring 说明取值语义 |
| 4 | delete 时若 id 已被用于标记的极端场景 (不可能, id 是主键自增) | 无需处理 |
| 5 | 与 F (全局过滤器) 的关系 | 谓词 `col == 0` 不变, 天然兼容 |

## 测试策略

1. oracle 对比测试: 删→建→删→建 循环, 断言每次 create 成功且唯一键约束从未被触发
2. restore 冲突: 显式 IntegrityError 断言
3. 过滤回归: 现有软删过滤测试在 Unique 变体上原样通过
4. 类创建期互斥校验: 同表同时继承两个软删 mixin → TypeError
5. 大 id 场景: id 超 smallint 上限的插入+删除 (SQLite 下模拟大值即可, 无需真 MySQL 数据量)
6. 成本验证 (`test_cost__*`, 语句记录器见 README): `test_cost__delete_by_id__same_as_baseline` —
   SoftDeleteUnique 变体与基线 `FieldIsDeleteSoftDeleteTableMixin` 的 delete_by_id 语句数逐项相等 (恒 1 条), 差异仅在 SET 值
7. collation 咨询: 唯一键在 8.0 `utf8mb4_0900_ai_ci` 下重音折叠 (`café`=`cafe`) 的撞键行为写入 mixin docstring 并有文档测试防漂移 (详见 [10 R5](./10-mysql-mode-compat.md))

## 非目标

- 不自动创建/迁移唯一索引 (DDL 归业务方迁移工具)
- 不做多列业务键的组合约定封装 (唯一键怎么建是 schema 设计自由)
- 不解决硬删场景 (硬删天然无此问题)
