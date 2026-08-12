# language: zh-CN

功能: 主键属性与审计列去魔法
  作为后端开发者
  我希望批量更新 / 乐观锁不隐式写审计列, 且支持自定义主键属性名

  背景:
    假设 数据库连接已就绪

  场景: 批量更新名称时不隐式写 update_datetime
    假设 使用 "标准CRUD" 作为当前 DAL
    并且 已存在一条名称为 "audit-batch" 的记录
    当 批量按当前实体 ID 条件更新名称为 "audit-batch-after"
    那么 返回的实体名称应为 "audit-batch-after"
    并且 数据库表中 ID 为当前实体 ID 的记录的 "update_datetime" 应为 "None"
    并且 数据库表中 ID 为当前实体 ID 的记录的 "update_operator_id" 应为 "None"

  场景: 乐观锁更新名称时不隐式写 update_datetime
    假设 使用 "乐观锁" 作为当前 DAL
    并且 已存在一条名称为 "audit-opt" 的记录
    当 乐观锁更新名称和值 (期望版本 0)
    那么 返回的实体不为空
    并且 数据库表中 ID 为当前实体 ID 的记录的 "update_datetime" 应为 "None"
    并且 数据库表中 ID 为当前实体 ID 的记录的 "update_operator_id" 应为 "None"
    并且 数据库表中 version 为 1

  场景: 自定义主键 user_id 可按主键查询与更新
    假设 使用 "自定义主键" 作为当前 DAL
    并且 已存在一条名称为 "custom-pk" 的记录
    当 通过 ID 查询该记录
    那么 返回的实体不为空
    并且 返回的实体名称应为 "custom-pk"
    当 使用新 CU 将记录名称更新为 "custom-pk-after"
    那么 返回的实体不为空
    并且 返回的实体名称应为 "custom-pk-after"
    并且 数据库表中 ID 为当前实体 ID 的记录的 "name" 应为 "custom-pk-after"
