# language: zh-CN

功能: DynamicDAL 只读保护
  作为后端开发者
  我希望 DynamicDAL 的写入操作在只读表上被拒绝

  背景:
    假设 DynamicDAL 只读表的数据库连接已就绪

  场景: 只读表查询正常
    当 DynamicDAL 查询只读表 ID 为 1 的记录
    那么 DynamicDAL 返回的 DTO 不为空

  场景: 只读表拒绝创建
    当 DynamicDAL 尝试在只读表创建记录
    那么 DynamicDAL 操作被阻止

  场景: 只读表拒绝更新
    当 DynamicDAL 尝试在只读表更新记录
    那么 DynamicDAL 操作被阻止

  场景: 只读表拒绝删除
    当 DynamicDAL 尝试在只读表删除记录
    那么 DynamicDAL 操作被阻止

  场景: 只读表拒绝批量创建
    当 DynamicDAL 尝试在只读表批量创建
    那么 DynamicDAL 操作被阻止
