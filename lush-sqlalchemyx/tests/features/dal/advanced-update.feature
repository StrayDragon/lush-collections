# language: zh-CN

功能: 高级更新策略
  作为后端开发者
  我希望能通过全量更新、部分更新、及各种 None 策略精确控制更新行为

  背景:
    假设 数据库连接已就绪
    假设 使用 "标准CRUD" 作为当前 DAL

  # ── update_only_set_by_id (none_policy) ──

  场景: only-set 默认 allow 显式 None 将描述置空
    假设 已存在一条名称为 "only-allow-init" 的记录
    并且 将该记录的描述设置为 "wipe"
    当 only-set 更新名称为 "only-allow-init" 且描述置空 (默认 allow)
    那么 返回的实体不为空
    并且 数据库表中 ID 为当前实体 ID 的记录的 "description" 应为 "None"

  场景: only-set 显式 ignore None 保留描述
    假设 已存在一条名称为 "only-ignore-init" 的记录
    并且 将该记录的描述设置为 "keep"
    当 only-set 更新名称为 "only-ignore-init" 且描述置空 (ignore None 策略)
    那么 返回的实体不为空
    并且 数据库表中 ID 为当前实体 ID 的记录的 "name" 应为 "only-ignore-init"
    并且 数据库表中 ID 为当前实体 ID 的记录的 "description" 应为 "keep"

  场景: only-set allow None 将描述置空
    假设 已存在一条名称为 "only-allow-explicit-init" 的记录
    并且 将该记录的描述设置为 "wipe"
    当 only-set 更新名称为 "only-allow-explicit-init" 且描述置空 (allow None 策略)
    那么 返回的实体不为空
    并且 数据库表中 ID 为当前实体 ID 的记录的 "description" 应为 "None"

  场景: only-set forbid None 抛出异常
    假设 已存在一条名称为 "only-forbid-init" 的记录
    并且 将该记录的描述设置为 "hello"
    当 only-set 更新描述置空 (forbid None 策略)
    那么 抛出了 ValueError

  # ── update_full_by_id ──

  场景: 全量更新已存在的记录
    假设 已存在一条名称为 "全量更新" 的记录
    并且 将该记录的值设置为 "10"
    当 全量更新记录名称为 "全量已更新" 值为 "20"
    那么 返回的实体不为空
    并且 数据库表中 ID 为当前实体 ID 的记录的 "name" 应为 "全量已更新"
    并且 数据库表中 ID 为当前实体 ID 的记录的 "value" 应为 "20"

  场景: 全量更新不存在的记录返回 None
    当 全量更新不存在的记录 ID "99999"
    那么 返回的实体为空

  # ── update_partial_by_id (none_policy variants) ──

  场景: 部分更新时 ignore None 保留原值
    假设 已存在一条名称为 "ignore-init" 的记录
    并且 将该记录的描述设置为 "hello"
    当 部分更新名称和值 (ignore None 策略)
    那么 返回的实体不为空
    并且 数据库表中 ID 为当前实体 ID 的记录的 "name" 应为 "ignore-init"
    并且 数据库表中 ID 为当前实体 ID 的记录的 "value" 应为 "99"

  场景: 部分更新时 allow None 将描述置空
    假设 已存在一条名称为 "allow-init" 的记录
    并且 将该记录的描述设置为 "hello"
    当 部分更新名称为 "allow-updated" 且描述置空 (allow None 策略)
    那么 返回的实体不为空
    并且 数据库表中 ID 为当前实体 ID 的记录的 "name" 应为 "allow-updated"
    并且 数据库表中 ID 为当前实体 ID 的记录的 "description" 应为 "None"

  场景: 部分更新时 forbid None 抛出异常
    假设 已存在一条名称为 "forbid-init" 的记录
    并且 将该记录的描述设置为 "hello"
    当 部分更新描述置空 (forbid None 策略)
    那么 抛出了 ValueError

  场景: 部分更新时 None policy 字段级覆盖
    假设 已存在一条名称为 "override-init" 的记录
    并且 将该记录的描述设置为 "hello"
    当 部分更新描述置空 (ignore 策略 + 覆盖为 allow)
    那么 返回的实体不为空
    并且 数据库表中 ID 为当前实体 ID 的记录的 "description" 应为 "None"

  场景: 部分更新 strict 模式检测未允许字段
    假设 已存在一条名称为 "strict-init" 的记录
    并且 将该记录的值设置为 "1"
    当 部分更新名称为 "strict-ok" 并尝试额外更新 description (strict 模式)
    那么 抛出了 ValueError

  场景: 部分更新不存在的记录返回 None
    当 部分更新不存在的记录 ID "99999"
    那么 返回的实体为空
