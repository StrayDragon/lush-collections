# language: zh-CN

功能: DynamicDAL 软删除行为
  作为后端开发者
  我希望 DynamicDAL 的删除操作为软删除
  以便支持数据恢复和审计追溯

  背景:
    假设 DynamicDAL 带软删除的数据库连接已就绪

  场景: 软删除后查询返回空
    假设 DynamicDAL 软删除表已存在一条名称为 "软删测试" 的记录
    当 DynamicDAL 删除该记录
    那么 DynamicDAL 返回的结果为 True
    并且 DynamicDAL 删除后查询结果为空

  场景: 软删除后列表排除已删除
    假设 DynamicDAL 软删除表已存在一条名称为 "列表A" 的记录
    并且 DynamicDAL 软删除表已存在一条名称为 "列表B" 的记录
    当 DynamicDAL 删除该记录
    那么 DynamicDAL 列表查询不包含已删除记录

  场景: 软删除后计数排除已删除
    假设 DynamicDAL 软删除表已存在一条名称为 "计数A" 的记录
    并且 DynamicDAL 软删除表已存在一条名称为 "计数B" 的记录
    当 DynamicDAL 删除该记录
    那么 DynamicDAL 软删除后计数正确

  场景: 恢复软删除的记录
    假设 DynamicDAL 软删除表已存在一条名称为 "恢复测试" 的记录
    当 DynamicDAL 删除该记录
    并且 DynamicDAL 恢复该记录
    那么 DynamicDAL 返回的结果为 True
    并且 DynamicDAL 恢复后查询结果不为空

  场景: 删除不存在的记录返回失败
    当 DynamicDAL 删除不存在的记录 ID "99999"
    那么 DynamicDAL 返回的结果为 False
