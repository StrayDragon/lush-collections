# language: zh-CN
功能: 基本 KV 操作
  测试 AsyncRedisPrefixedOp 的 CRUD 操作, 包括 set/get/delete/exists/ttl/expire 及 key_prefix 前缀拼接

  场景: 设置并获取键值
    假设 已使用 prefixed 操作 ":test:"
    当 设置键 "mykey" 值为 "hello"
    那么 返回结果应为 True
    并且 原始键 ":test:mykey" 应存在
    并且 原始键 ":test:mykey" 的值应为 "hello"

  场景: 获取不存在的键返回默认值
    假设 已使用 prefixed 操作 ":test:"
    并且 Redis 键 ":test:missing" 不存在
    当 获取键 "missing" 的值
    那么 返回的值应为 "__notfound__"

  场景: 设置并获取过期时间
    假设 已使用 prefixed 操作 ":test:"
    当 设置键 "withttl" 值为 "v" 且过期时间为 "10" 秒
    那么 原始键 ":test:withttl" 的 TTL 应大于 "0"

  场景: 过期时间过后键消失
    假设 已使用 prefixed 操作 ":test:"
    当 设置键 "ephemeral" 值为 "tmp" 且过期时间为 "1" 秒
    那么 原始键 ":test:ephemeral" 应存在
    当 等待 "1.200000" 秒
    那么 原始键 ":test:ephemeral" 应不存在

  场景: 删除已存在的键
    假设 已使用 prefixed 操作 ":test:"
    当 设置键 "delme" 值为 "x"
    那么 原始键 ":test:delme" 应存在
    当 删除键 "delme"
    那么 返回的值应为 "1"
    并且 原始键 ":test:delme" 应不存在

  场景: 删除不存在的键返回 0
    假设 已使用 prefixed 操作 ":test:"
    并且 Redis 键 ":test:ghost" 不存在
    当 删除键 "ghost"
    那么 返回的值应为 "0"

  场景: 检查键存在性
    假设 已使用 prefixed 操作 ":test:"
    当 设置键 "exist" 值为 "1"
    当 检查键 "exist" 是否存在
    那么 返回的值应为 "1"

  场景: 检查不存在的键
    假设 已使用 prefixed 操作 ":test:"
    并且 Redis 键 ":test:nobody" 不存在
    当 检查键 "nobody" 是否存在
    那么 返回的值应为 "0"

  场景: 设置 JSON 值并读取
    假设 已使用 prefixed 操作 ":test:"
    当 设置键 "json" 的 JSON 数据为 简单字典
    那么 原始键 ":test:json" 应存在
    当 获取键 "json" 的 JSON 值
    那么 返回值为 JSON 且值等于 简单字典

  场景: 设置 JSON 键 NX - 键不存在时创建成功
    假设 已使用 prefixed 操作 ":test:"
    并且 Redis 键 ":test:jsonnx" 不存在
    当 设置键 "jsonnx" 的 NX JSON 数据为 单键值对
    那么 返回结果应为 True
    并且 原始键 ":test:jsonnx" 应存在

  场景: 设置 JSON 键 NX - 键已存在时失败
    假设 已使用 prefixed 操作 ":test:"
    并且 Redis 键 ":test:jsonnx2" 已存在且值为 "something"
    当 设置键 "jsonnx2" 的 NX JSON 数据为 小字典
    那么 返回结果应为 False

  场景: 设置超时时间
    假设 已使用 prefixed 操作 ":test:"
    当 设置键 "e" 值为 "1"
    当 将键 "e" 超时时间设为 "5" 秒
    那么 返回结果应为 True
    并且 原始键 ":test:e" 的 TTL 应大于 "0"

  场景: 对不存在的键设置超时返回 False
    假设 已使用 prefixed 操作 ":test:"
    并且 Redis 键 ":test:noe" 不存在
    当 将键 "noe" 超时时间设为 "5" 秒
    那么 返回结果应为 False
