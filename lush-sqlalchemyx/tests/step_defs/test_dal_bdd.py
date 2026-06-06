"""BDD 场景入口 — 将 .feature 文件中的场景注册为 pytest 测试.

注意: 所有 Then 步骤使用裸 SQLAlchemy 验证数据库物理状态,
确保测试不依赖被测代码自身来验证结果.
"""

from pytest_bdd import scenario

# ── basic-crud.feature ──

@scenario("dal/basic-crud.feature", "创建新记录并返回实体")
def test_create_returns_entity() -> None: ...

@scenario("dal/basic-crud.feature", "创建记录并返回 DTO")
def test_create_returns_dto() -> None: ...

@scenario("dal/basic-crud.feature", "通过 ID 查询已存在的记录")
def test_get_by_id_existing() -> None: ...

@scenario("dal/basic-crud.feature", "通过 ID 查询不存在的记录")
def test_get_by_id_nonexistent() -> None: ...

@scenario("dal/basic-crud.feature", "检查记录是否存在")
def test_exists_record() -> None: ...

@scenario("dal/basic-crud.feature", "更新已存在的记录")
def test_update_record() -> None: ...

@scenario("dal/basic-crud.feature", "删除已存在的记录")
def test_delete_record() -> None: ...

@scenario("dal/basic-crud.feature", "统计记录总数")
def test_count_records() -> None: ...

# ── soft-delete.feature ──

@scenario("dal/soft-delete.feature", "删除记录后查询返回空 (软删除可见性)")
def test_soft_delete_visibility() -> None: ...

@scenario("dal/soft-delete.feature", "删除不存在的记录返回失败")
def test_soft_delete_nonexistent() -> None: ...

@scenario("dal/soft-delete.feature", "更新被软删除的记录无副作用")
def test_soft_delete_bystander_preserved() -> None: ...

@scenario("dal/soft-delete.feature", "创建后立即删除返回一致结果")
def test_create_then_delete_consistent() -> None: ...

# ── advanced-update.feature ──

@scenario("dal/advanced-update.feature", "全量更新已存在的记录")
def test_update_full_existing() -> None: ...

@scenario("dal/advanced-update.feature", "全量更新不存在的记录返回 None")
def test_update_full_nonexistent() -> None: ...

@scenario("dal/advanced-update.feature", "部分更新时 ignore None 保留原值")
def test_update_partial_ignore_none() -> None: ...

@scenario("dal/advanced-update.feature", "部分更新时 allow None 将描述置空")
def test_update_partial_allow_none() -> None: ...

@scenario("dal/advanced-update.feature", "部分更新时 forbid None 抛出异常")
def test_update_partial_forbid_none() -> None: ...

@scenario("dal/advanced-update.feature", "部分更新时 None policy 字段级覆盖")
def test_update_partial_none_override() -> None: ...

@scenario("dal/advanced-update.feature", "部分更新 strict 模式检测未允许字段")
def test_update_partial_strict() -> None: ...

@scenario("dal/advanced-update.feature", "部分更新不存在的记录返回 None")
def test_update_partial_nonexistent() -> None: ...

# ── batch-ops.feature ──

@scenario("dal/batch-ops.feature", "批量按 ID 查询实体")
def test_batch_get_entities() -> None: ...

@scenario("dal/batch-ops.feature", "批量按 ID 查询空列表")
def test_batch_get_empty() -> None: ...

@scenario("dal/batch-ops.feature", "批量按 ID 查询返回 DTO")
def test_batch_get_dtos() -> None: ...

@scenario("dal/batch-ops.feature", "批量按 name 字段查询")
def test_batch_get_field() -> None: ...

@scenario("dal/batch-ops.feature", "批量按 name 字段查询空列表")
def test_batch_get_field_empty() -> None: ...

@scenario("dal/batch-ops.feature", "批量按 ID 更新")
def test_batch_update_by_ids() -> None: ...

@scenario("dal/batch-ops.feature", "批量按 ID 更新空列表")
def test_batch_update_empty() -> None: ...

@scenario("dal/batch-ops.feature", "批量按条件更新名称")
def test_batch_update_by_conditions() -> None: ...

@scenario("dal/batch-ops.feature", "批量按条件更新值")
def test_batch_update_conditions_value() -> None: ...

@scenario("dal/batch-ops.feature", "批量更新无效 key 抛出异常")
def test_batch_update_invalid_key() -> None: ...

# ── readonly-guard.feature ──

@scenario("dal/readonly-guard.feature", "update_only_set 在只读会话被阻止")
def test_readonly_update_only_set() -> None: ...

@scenario("dal/readonly-guard.feature", "update_full 在只读会话被阻止")
def test_readonly_update_full() -> None: ...

@scenario("dal/readonly-guard.feature", "update_partial 在只读会话被阻止")
def test_readonly_update_partial() -> None: ...

@scenario("dal/readonly-guard.feature", "delete 在只读会话被阻止")
def test_readonly_delete() -> None: ...

@scenario("dal/readonly-guard.feature", "batch_update 在只读会话被阻止")
def test_readonly_batch_update() -> None: ...

@scenario("dal/readonly-guard.feature", "optimistic_lock 在只读会话被阻止")
def test_readonly_opt_lock() -> None: ...

# ── iterators.feature ──

@scenario("dal/iterators.feature", "遍历全部记录")
def test_iter_all_records() -> None: ...

@scenario("dal/iterators.feature", "按条件遍历")
def test_iter_with_where() -> None: ...

@scenario("dal/iterators.feature", "遍历返回 DTO")
def test_iter_dtos() -> None: ...

# ── optimistic-lock.feature ──

@scenario("dal/optimistic-lock.feature", "版本号匹配时更新成功")
def test_optimistic_lock_success() -> None: ...

@scenario("dal/optimistic-lock.feature", "版本号不匹配时抛出冲突错误")
def test_optimistic_lock_conflict() -> None: ...

@scenario("dal/optimistic-lock.feature", "乐观锁空更新返回实体")
def test_optimistic_lock_empty_update() -> None: ...

@scenario("dal/optimistic-lock.feature", "乐观锁更新并 refresh")
def test_optimistic_lock_with_refresh() -> None: ...

@scenario("dal/optimistic-lock.feature", "无 version 字段的表触发 AttributeError")
def test_optimistic_lock_no_version() -> None: ...

@scenario("dal/optimistic-lock.feature", "乐观锁更新不存在的记录抛出异常")
def test_optimistic_lock_nonexistent() -> None: ...

# ── for-update-sql.feature ──

@scenario("dal/for-update-sql.feature", "通过 ID 加悲观锁查询")
def test_for_update_by_id() -> None: ...

@scenario("dal/for-update-sql.feature", "批量加悲观锁查询")
def test_batch_for_update() -> None: ...

@scenario("dal/for-update-sql.feature", "批量加悲观锁查询空列表")
def test_batch_for_update_empty() -> None: ...

@scenario("dal/for-update-sql.feature", "按条件加悲观锁查询单条记录")
def test_get_one_for_update() -> None: ...

@scenario("dal/for-update-sql.feature", "执行裸 SQL")
def test_execute_sql() -> None: ...

# ── retry.feature ──

@scenario("dal/retry.feature", "重试后最终成功")
def test_retry_success() -> None: ...

@scenario("dal/retry.feature", "重试耗尽后抛出异常")
def test_retry_exhausted() -> None: ...
