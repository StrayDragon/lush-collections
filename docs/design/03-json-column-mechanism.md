# 03 — JSON 列机制: 现状盘点与小步增强

> 状态: **提案 (未实现)** — 本文档是对**已在生产使用机制**的盘点 + 两个低风险增强, 不是新机制提案.
> 影响包: `lush-pydanticx` (SSOT 所在), `lush-sqlalchemyx` (`FieldMixin.DataJsonBytes` 增强)
> ~~原方向~~: PydanticJSON TypeDecorator (驱动层方案) → **已否决**, 见 [非目标](#非目标)

## 背景与动机: 已有机制的完整盘点

JSON 列承载结构化数据的方案**已经存在且在用**, 分三层协作:

| 层 | 机制 | 位置 | 职责 |
|----|------|------|------|
| 物理列 | `Mapped[bytes]` + `sa.LargeBinary` | ORM 表 | 纯存储, 无类型语义 |
| 模型层 (SSOT) | `DataJson[M]` (= `Json[M] \| M`) + `@field_serializer` + `json_to_bytes_serializer` | `lush_pydanticx`, 声明在 CU/DTO | 写路径序列化 (dump→bytes) + 读路径解析 (bytes→模型) |
| 实体侧 | `FieldMixin.DataJsonBytes[M]` property mixin | `lush_sqlalchemyx._common` | ORM 实体上的便捷访问器 `x_data_json` |

标准用法 (摘自 `tests/test_base_dal.py` 的真实测试表):

```python
from lush_pydanticx import DataJson, json_to_bytes_serializer

class JobTable(Base):
    __tablename__ = "job"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    data_json: Mapped[bytes] = mapped_column(sa.LargeBinary, default=b"{}")

class JobCU(BaseCU[JobTable]):
    _Table = JobTable
    data_json: DataJson[JobPayload] = JobPayload()      # ① 校验层: 接受模型实例或 JSON 字符串

    @field_serializer("data_json")                       # ② 序列化: dump 时出 bytes
    def serialize_data_json(self, value: Any) -> bytes:
        return json_to_bytes_serializer(value)

class JobDTO(JobCU, BaseDTO[JobCU]): ...                 # ③ 读回: Json[T] 把实体 bytes 解析成模型
```

### 行为基线 (已实测验证)

```
读: DTO.model_validate({"data_json": b'{"title":"from-db"}'})
    → JobPayload 实例            # Json[T] 直接接住 raw bytes ✓
写: cu.model_dump(exclude_unset=True)
    → {"data_json": b'{"title":"w","tags":[]}'}   # field_serializer 自动生效 ✓
```

**关键结论**: 序列化发生在 CU/DTO 的 dump 阶段, 而 ORM/Core/Dynamic 三条 DAL 写路径都经过
`model_dump` —— 因此三条路径的写入已被现状机制全覆盖, **不存在需要驱动层补的洞**.

## 待改进点 (真实痛点)

| # | 痛点 | 现状 |
|---|------|------|
| 1 | 实体侧 mixin 需手动绑定泛型 | `class T(...DataJsonBytes[DM])` 后还要补一行 `T._DATA_JSON = DM` (见现有测试写法) |
| 2 | `@field_serializer` 三行样板/字段 | 每个含 JSON 模型的字段手写一次 |

## 增强提案

### E1: mixin 泛型自动绑定 (核心增强)

`DataJsonBytes.__init_subclass__` 从 `__orig_bases__` 中捕获订阅时的模型参数,
自动设置 `_DATA_JSON`; 显式赋值的旧写法仍然优先 (向后兼容):

```python
# ── after ──────────────────────────────────────────
class JobTable(Base, FieldMixin.DataJsonBytes[JobPayload]):
    __tablename__ = "job"
    data_json: Mapped[bytes] = mapped_column(sa.LargeBinary, default=b"{}")
    # 不再需要: JobTable._DATA_JSON = JobPayload

entity.data_json          # bytes
entity.x_data_json        # JobPayload 实例 (property 行为不变)

# ── 兼容矩阵 ────────────────────────────────────────
class OldStyle(Base, FieldMixin.DataJsonBytes[JobPayload]): ...
OldStyle._DATA_JSON = OtherPayload   # 显式赋值仍生效, 自动绑定让位
```

**机制已原型验证** (2026-08, sqlalchemyx venv):

```python
def __init_subclass__(cls, **kwargs: Any) -> None:
    super().__init_subclass__(**kwargs)
    if "_DATA_JSON" in cls.__dict__:
        return                                    # 显式声明优先
    for base in getattr(cls, "__orig_bases__", ()):
        origin = get_origin(base)
        if origin is not None and isinstance(origin, type) and issubclass(origin, DataJsonBytes):
            args = get_args(base)
            if args and isinstance(args[0], type) and issubclass(args[0], BaseModel):
                cls._DATA_JSON = args[0]
                return
```

注意实现细节:

- 必须加在 `DataJsonBytes` 自身 (它是 `Generic` 子类); 在其普通子类上加会因丢失泛型性而失效
- 多重继承时 SQLAlchemy declarative 与该 hook 共存无冲突 (已验证)
- 未订阅泛型的旧式子类行为不变 (循环找不到匹配参数即静默跳过, 回落到显式赋值/报错路径)

**成本特征** (实现期须写入 `x_data_json` docstring): property 每次访问都重新
decode + `model_validate_json`, O(JSON 体积) —— **无缓存**. 同一实体的模型需多次使用时
应先存局部变量; 该行为与现状 mixin 一致, E1 不改变它 (引入缓存属行为变更, 需单独评估失效策略).

### E2: 标准配方文档化 (样板问题明确接受)

Pydantic v2 不支持"注解驱动的 serializer 注入" (`Annotated` 元数据无法自动生成 `field_serializer`),
后处理注入需重新构造模型类, 成本与收益倒挂.

结论: **三行样板作为显式成本接受**, 在 `lush-pydanticx` docstring / README 补一份完整配方
(含 DTO 继承 CU 的读路径说明), 并在配方中强调:

- `DataJson[M]` 字段的 patch 语义: 整字段替换, 不存在部分更新 (与 02 Spread 的 exclude_unset 交互不适用)
- 实体上原地修改 `entity.data_json` bytes 不标脏 —— JSON 模型的修改必须走「CU 更新」路径

## 预期效果汇总

| 场景 | 现状 | E1 之后 |
|------|------|---------|
| 声明含 JSON 模型列的表 | 表类 + 事后 `_DATA_JSON` 赋值 (两处) | 表类一处声明 |
| 新人上手 | 需要知道隐藏的类变量约定 | 泛型参数即声明 |
| 既有代码迁移 | — | 零改动 (兼容矩阵保证) |

## 测试策略

1. 自动绑定: 订阅泛型 / 显式赋值优先 / 未订阅回落 / 多级继承 四态单测
2. 回归: 现有 `TestDataJsonFields` / `TestDataJsonBytesField` / `TestFieldMixinDataJsonBytes` 全部原样通过
3. 配方文档的示例代码进 doctest 或示例测试, 防漂移
4. 成本验证 (`test_cost__*`, 语句记录器见 README): `test_cost__auto_bind__zero_sql` — 类创建期自动绑定与
   `x_data_json` 访问 ledger.count 恒为 0 (纯内存契约; 重解析成本属 CPU 特性, 以量级描述保留, 不入 CI)

## 非目标

- **PydanticJSONType (TypeDecorator, 驱动层方案) — 否决**. 与 `DataJson`(Pydantic 层) 同目的不同层,
  引入即双轨心智模型; 而它换来的两点好处 (免 serializer 样板、实体属性直访模型) 分别被 E2 (接受显式)
  和 E1 (mixin 增强) 以更低成本覆盖. 若未来出现"Core 直插模型对象、绕过 CU"的真实高频场景再重启评估.
- 不改物理存储格式 (维持 LargeBinary bytes); 换 `sa.JSON` 列属业务方自由, 但失去本机制的解析层
- 不做多 JSON 模型字段的单表混挂 (现设计即单 `_DATA_JSON_FIELD`, 保持)
