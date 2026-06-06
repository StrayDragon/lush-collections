# language: zh-CN

功能: 乐观锁并发控制
  作为后端开发者
  我希望通过版本号实现并发更新的冲突检测

  背景:
    假设 数据库连接已就绪
    假设 使用 "乐观锁" 作为当前 DAL

  场景: 版本号匹配时更新成功
    假设 已存在一条名称为 "opt-ok" 的记录
    并且 将该记录的值设置为 "10"
    当 乐观锁更新名称和值 (期望版本 0)
    那么 返回的实体不为空
    并且 返回的实体名称应为 "opt-updated"
    并且 数据库表中 version 为 1

  场景: 版本号不匹配时抛出冲突错误
    假设 已存在一条名称为 "opt-conflict" 的记录
    当 乐观锁更新 (期望错误版本 999)
    那么 抛出了 DBRetryableError

  场景: 乐观锁空更新返回实体
    假设 已存在一条名称为 "opt-empty" 的记录
    当 乐观锁空更新
    那么 返回的实体不为空

  场景: 乐观锁更新并 refresh
    假设 已存在一条名称为 "opt-refresh" 的记录
    当 乐观锁更新并 refresh
    那么 返回的实体不为空
    并且 返回的实体名称应为 "opt-refreshed"

  场景: 无 version 字段的表触发 AttributeError
    假设 使用 "简单CRUD" 作为当前 DAL
    并且 已存在一条名称为 "no-version" 的记录
    当 使用简单 DAL 乐观锁更新 (无 version 字段)
    那么 抛出了 AttributeError

  场景: 乐观锁更新不存在的记录抛出异常
    假设 使用 "乐观锁" 作为当前 DAL
    当 乐观锁更新不存在的记录 ID "99999"
    那么 抛出了 DBRetryableError
