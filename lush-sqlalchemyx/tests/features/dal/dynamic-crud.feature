# language: zh-CN

功能: DynamicDAL 基础 CRUD
  作为后端开发者
  我希望通过 DynamicDAL (无需 ORM Table class) 进行基本的增删改查
  以便快速操作已有 schema 的表

  背景:
    假设 DynamicDAL 数据库连接已就绪

  场景: 创建记录并返回 DTO
    当 DynamicDAL 创建一条名称为 "新记录" 的记录
    那么 DynamicDAL 返回的 DTO 不为空
    并且 DynamicDAL 返回的 DTO 名称应为 "新记录"

  场景: 通过 ID 查询已存在的记录
    假设 DynamicDAL 已存在一条名称为 "查询测试" 的记录
    当 DynamicDAL 通过 ID 查询该记录
    那么 DynamicDAL 返回的 DTO 不为空
    并且 DynamicDAL 返回的 DTO 名称应为 "查询测试"

  场景: 通过 ID 查询不存在的记录
    当 DynamicDAL 查询不存在的记录 ID "99999"
    那么 DynamicDAL 返回的结果为空

  场景: 更新已存在的记录
    假设 DynamicDAL 已存在一条名称为 "更新前" 的记录
    当 DynamicDAL 使用新 CU 将记录名称更新为 "更新后"
    那么 DynamicDAL 返回的受影响行数为 1

  场景: 删除已存在的记录 (硬删除)
    假设 DynamicDAL 已存在一条名称为 "待删除" 的记录
    当 DynamicDAL 删除该记录
    那么 DynamicDAL 返回的结果为 True

  场景: 批量创建记录
    当 DynamicDAL 批量创建 3 条记录
    那么 DynamicDAL 批量创建返回 3
    并且 DynamicDAL 列表查询至少有 3 条

  场景: 条件查询
    假设 DynamicDAL 已存在一条名称为 "条件测试" 的记录
    当 DynamicDAL 按条件查询名称为 "条件测试"
    那么 DynamicDAL 条件查询结果至少有 1 条

  场景: 条件计数
    假设 DynamicDAL 已存在一条名称为 "计数测试" 的记录
    当 DynamicDAL 统计记录总数
    那么 DynamicDAL 返回的记录总数至少为 1
