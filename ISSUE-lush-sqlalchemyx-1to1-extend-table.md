# [lush-sqlalchemyx] 1:1 水平扩展表 (shared PK) 的一等支持

> 状态: **已落地 (P0)** — 见 `BaseCU.cu_config` / `EXTEND_TABLE_CU_CONFIG` / `DynamicTableConfig.exclude_pk_on_create`
> 影响包: `lush-sqlalchemyx`, `lush-dal-protocol`
> 来源: 异步后台任务系统 Producer 侧实践 (主表 + `job_type` 扩展表)

## 背景

业务上常见「通用主表 + 按类型水平拆分的 1:1 扩展表」:

- 主表: 通用状态机 + 运行态 JSON (`data_json`)
- 扩展表: 提交参数快照 + 结构化查询列 (`export_function` 等)
- 关系: `extend.id = main.id` (共享主键, **扩展表不自增**)

提交时序: **同一事务** 内先 INSERT 主表 (拿自增 id) → 再 INSERT 扩展表 (显式 id).

## 已落地方案

### ORM: `BaseCU.cu_config` (对标 Pydantic `model_config`)

```python
from lush_sqlalchemyx.base.dal import BaseCU, EXTEND_TABLE_CU_CONFIG

class ExtendCU(BaseCU[ExtendTable]):
    _Table = ExtendTable
    cu_config = EXTEND_TABLE_CU_CONFIG  # 或 BaseCUConfigDict(to_orm_exclude=frozenset())
    id: int
    report_name: str
```

- `to_orm_exclude` / `update_exclude`: `frozenset[str]`, 默认均为 `frozenset({"id"})`
- MRO 浅合并 (子类已设覆盖, 未设继承上游); `__init_subclass__` 缓存
- 扩展表 **必须独立 DAL**; 禁止用主表 DAL 的 `create` 写扩展行

```python
main_dto = await main_dal.ret_dto_after_create(session, main_cu)
extend_dto = await extend_dal.ret_dto_after_create(
    session, ExtendCU(id=main_dto.id, report_name=...),
)
```

### Dynamic: `exclude_pk_on_create=False`

```python
ref = TableRef(
    table_name="...",
    config=DynamicTableConfig(exclude_pk_on_create=False),
    _dto_class=ExtendDTO,
)
```

update 路径始终排除 PK (`cu_row_data(..., for_create=False)`).

## 验收 (P0)

- [x] 扩展表 CU 无需手写 `to_orm_model` 即可保留 `id`
- [x] 文档明确: 扩展表必须独立 DAL
- [x] 测试覆盖 shared-PK CU + extend DAL create / update; Dynamic 显式 PK

## 非目标 / 后置

- 不强制 SQLAlchemy `relationship()` / 级联插入
- 不替代 Dynamic DAL
- 不要求框架感知具体 `job_type` 业务语义
- P1 `PairedCreateMixin` / P2 JOIN 组装 helper — 按需另开

## 关联

- `lush-dal-protocol.dto`: `BaseCUConfigDict`, `EXTEND_TABLE_CU_CONFIG`, `BaseCU.resolve_cu_config`
- `lush-pydanticx`: `DataJson`, `json_to_bytes_serializer`
