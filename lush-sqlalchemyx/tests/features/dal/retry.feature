# language: zh-CN

功能: 重试机制
  作为后端开发者
  我希望能自动重试可恢复的数据库冲突错误

  背景:
    假设 数据库连接已就绪
    假设 使用 "标准CRUD" 作为当前 DAL

  场景: 重试后最终成功
    当 使用 sync_with_retry 执行会成功重试的操作
    那么 返回的实体不为空

  场景: 重试耗尽后抛出异常
    当 使用 sync_with_retry 执行总是失败的操作
    那么 抛出了 DBRetryableError
