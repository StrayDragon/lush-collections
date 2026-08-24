# 11 — 类型与测试工程规范 (横切关注点)

> 状态: **部分落地** — 已落地: §5 标记体系 + `--strict-markers`、§4 hypothesis 依赖与 CI derandomize profile、
> §3 `DynamicTableConfig` slots 加固、两包 AGENTS.md 规则节、首批属性测试
> (`lush-sqlalchemyx/tests/test_property_primitives.py`, `lush-dal-protocol/tests/test_property_dto_merge.py`).
> 未落地 (随对应 pattern 实现): §2 提取契约的固化测试 (Spread/FilterModel 尚未实现)、
> §4 表中 02/05/06/09 的 pattern 属性测试、§6 DoD 中 cost 对应关系脚本化 (P1).
> 影响包: `lush-sqlalchemyx`, `lush-dal-protocol` (约定层); 新增 dev 依赖候选: `hypothesis`
> 关联: [README 类型纪律](./README.md#api-设计与类型纪律-full-typing--坑点最少化) / [10 兼容性](./10-mysql-mode-compat.md)

## 1. 泛型纪律 (TypeVar Rules)

| 规则 | 说明 |
|------|------|
| 禁止裸 `TypeVar("T")` 进入公共签名 | 一切新 TypeVar 必须 `bound=` 或 `constrained=`; 存量 `SQLATableT`(unbounded) 是历史例外, 不新增也不回改 |
| 默认值用 `typing_extensions.TypeVar(default=...)` | 让部分特化可用: 只写前 N 个参数也能得到精确类型 (py3.10 无 PEP 695) |
| 泛型参数顺序全局一致 | `Session → Table → DTO → CU → PrimaryKey`, 与既有 `BaseDAL` 对齐; 新泛型类的 docstring 必须逐个列出参数含义 |
| 类级 TypeVar 保持 invariant | 不为"好看"声明 covariant —— 参数出现在属性赋值位置时协变是不健全的 |
| 结构匹配才用 Protocol | 定义"下游必须继承"的契约 → ABC (现有惯例); 定义"长得对就行"的消费方 (如 08 的 `HasChildren`) → `Protocol`; `@runtime_checkable` 仅在确需 isinstance 时加 |

## 2. Annotated 元数据提取契约 (Spread / FilterModel 的共同地基)

02 的 `Spread(prefix=...)` 与 05 的操作符后缀都藏在类型注解里, 提取机制有三条已知深坑, 全部固化为规则 + 测试:

1. **必须 `get_type_hints(..., include_extras=True)`** —— 不带该参数会剥掉全部 `Annotated` 元数据,
   静默拿到裸类型 (不报错、直接丢功能)。固化测试: 声明含 Spread 的模型, 断言提取到 prefix。
2. **`from __future__ import annotations` 下的命名空间**: 注解全是字符串, 提取时机必须在能解析
   引用的模块上下文; 统一约定在 `__init_subclass__` 中执行 (此时类所属模块可定位)。
3. **Pydantic 双通道**: 运行期字段元数据以 `type(X).model_fields[i].metadata` 为准 (Pydantic 自己保留
   Annotated), 非注解反射 —— 两通道结果一致性也入测试。

提取产物统一缓存为 frozen 类属性 (`_resolved_*` 命名), 与 `_resolved_cu_config` 同风格;
**一律使用 `type(X).model_fields`, 不做实例访问** (Pydantic 2.11+ 已弃用后者)。

## 3. 配置对象的严格化 (slots + frozen)

一切新的声明式配置/spec 对象 (DynamicTableConfig 后继者、GlobalFilterSpec、Spread 规格等):

```python
@dataclass(frozen=True, slots=True)
class GlobalFilterSpec: ...
```

- `frozen=True`: 配置被意外修改立即报错 (而非静默影响后续查询)
- `slots=True`: **拼写错误的属性赋值在赋值瞬间报错** (`spec.soft_delete_col = ...` → AttributeError),
  这是运行期的 typo 防线, 与类型检查互补

## 4. 属性测试 (property-based testing) — 提案新增 dev 依赖 `hypothesis`

适用判定: **纯 Python、无 IO、能写出可陈述不变量**的原语才值得属性测试; 生成策略必须有界。

| 原语 | 不变量 (property) | 生成策略 |
|------|-------------------|----------|
| 02 flatten/unflatten | 往返恒等: `unflatten(flatten(d)) == d`; patch 字段集在往返后保持 | 受控字典生成器 (仅合法字段名) |
| 05 后缀解析器 | 非法后缀必报错; 合法输入产出的谓词引用列 ∈ 表列集合 | 字段名 × 操作符组合生成 |
| 06 流转图 | TRANSITIONS 的可达闭包与声明一致; 图中不存在自环 | 小型有向图生成器 |
| 09 删建循环 | 任意次「删→建同名」循环后, 存活行仍可插入且唯一键从未冲突 | 小模型随机序列 |

决策点见文末。CI 归属: property 测试挂 `property` 标记进 unit job (**不在 mysql matrix 里重复跑**);
本地全量、CI 固定 seed (`derandomize=True`) 保证可复现。

## 5. 测试分层与标记体系

现状缺口: pytest 未注册自定义 markers, 也未开 `--strict-markers` (拼错 marker 名只会告警)。

```
[tool.pytest.ini_options]
markers = [
  "unit: 纯单元测试, 无外部依赖",
  "oracle: oracle 对比测试 (sqlite 或同构)",
  "matrix: 需要 MySQL 容器的矩阵测试",
  "compat: mysql mode × version 兼容性子集 (双 sql_mode 参数化)",
  "cost: 成本契约验证 (语句数断言)",
  "property: hypothesis 属性测试",
]
addopts 追加 --strict-markers
```

- 每份 pattern 文档「测试策略」里的每一条, 都必须归入上述标记之一 (评审时检查)
- 分层金字塔: `unit` (无 IO) 为最大体量 → `oracle` (sqlite) → `matrix` (mysql 抽样) / `compat` 子集;
  不设硬性数量比, 但评审关注分布是否倒挂
- CI job 映射: unit+oracle+cost+property 进快速 job; matrix/compat 进容器 job (沿用现有 matrix 工作流)

## 6. 里程碑 DoD (Definition of Done) 检查单

每个里程碑合并前逐项过:

- [ ] `ruff check` + `ruff format` 零差异
- [ ] basedpyright `--level error` 全绿 (含测试目录按现行宽松配置)
- [ ] 100% branch coverage; 如新增 omit 条目已在 AGENTS.md 记录理由
- [ ] 公共 API docstring: 中文; 触发成本强制范围的带「成本」段; L2 变更带迁移指引文本
- [ ] sync/async 镜像对照清单过一遍 (方法名、签名、语义三查)
- [ ] `__all__` 更新; 内部助手保持下划线私有 (公共 API 边界守则)
- [ ] 新增配置对象均为 `frozen=True, slots=True`
- [ ] 成本声明 ↔ cost 测试对应关系自查 (P1 脚本就绪前以 grep 清单代替)
- [ ] 涉及 protocol 的能力: InMemory 参考实现先行证明 conformance 套件自身正确
- [ ] CHANGELOG 条目 (minor/major); L2/L3 变更附升级说明

## 7. 类型学限制登记表 (静态到不了的地方汇总)

分散在各文档的"静态诚实声明"在此集中登记, 新增限制必须入表:

| 位置 | 静态形态 | 运行期补偿 | 固化测试 |
|------|---------|-----------|---------|
| 02 `project()` 返回 | `type[BaseModel]` (字段不可见) | 即时校验 + did-you-mean; 高频场景引导手写子集模型 | memoize identity / 越权 AttributeError |
| 01 `compose_full_dto` | 同上 | 手写 mixin 继承为主, 工厂只做冲突断言 | 重名字段 TypeError 测试 |
| 06 流转载荷 | CU 联合类型 (无法按边收窄) | 运行期查 PAYLOADS 边绑定 | 载荷错配 TypeError 测试 |
| 03 JSON 自动绑定 | 泛型参数经 `__orig_bases__` 运行期捕获 | 显式赋值优先的兼容矩阵 | 四态单测 |

## 待决策项 (Open Decisions)

| # | 决策点 | 当前倾向 |
|---|--------|----------|
| 1 | `hypothesis` 是否引入 | **引入**, dev 依赖组锚定版本; 上表 4 处原语是首批受益者, 收益 (边界自动发现) 明显大于依赖成本 |
| 2 | `--strict-markers` 开启 | 开启。存量测试若存在未注册 marker 会立刻暴露 —— 正是想要的效果 |
| 3 | 测试文件是否收紧 basedpyright | 维持现行宽松配置不动 (tests 目录 reportUnknown* = false); 类型收紧优先花在生产代码上 |
| 4 | property 测试的 CI seed 策略 | `derandomize=True` 进 CI (可复现优先); 本地探索用随机模式 |

## 非目标

- 不重写存量代码的泛型 (如 SQLATableT bound 化) —— 仅约束增量
- 不引入 mypy 双检查器 / 不追求 tests 目录 full typing (与现行配置冲突, 收益低)
- 不做突变测试 (mutmut 等) —— coverage 100% + 属性测试已覆盖主要风险面, 成本收益不划算
