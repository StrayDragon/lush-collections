# language: zh-CN
功能: 分布式锁
  测试 AsyncRedisPrefixedOp 的 simple_distributed_lock: 获取、释放、冲突检测、超时重获取

  场景: 成功获取并释放锁
    假设 已使用 prefixed 操作 ":test:"
    并且 Redis 键 ":test:lock:basic" 不存在
    当 尝试获取分布式锁 "lock:basic" 超时 "10" 秒
    那么 返回结果应为 True
    并且 原始键 ":test:lock:basic" 应存在
    并且 原始键 ":test:lock:basic" 的值应为 "1"
    并且 原始键 ":test:lock:basic" 的 TTL 应大于 "0"
    并且 原始键 ":test:lock:basic" 的 TTL 应小于等于 "10"
    当 释放分布式锁 "lock:basic"
    那么 原始键 ":test:lock:basic" 应不存在

  场景: 锁已被占用时获取失败
    假设 已使用 prefixed 操作 ":test:"
    并且 Redis 键 ":test:lock:busy" 已存在且值为 "pre-occupied" 且过期时间为 "10" 秒
    当 在已持有锁 "lock:busy" 的情况下, 尝试再次获取分布式锁 "lock:busy" 超时 "10" 秒
    那么 返回结果应为 False
    并且 原始键 ":test:lock:busy" 应存在

  场景: 锁超时后重新获取
    假设 已使用 prefixed 操作 ":test:"
    并且 Redis 键 ":test:lock:expire" 不存在
    当 尝试获取分布式锁 "lock:expire" 超时 "1" 秒
    那么 返回结果应为 True
    并且 原始键 ":test:lock:expire" 应存在
    当 释放分布式锁 "lock:expire"
    当 等待 "1.200000" 秒
    那么 原始键 ":test:lock:expire" 应不存在
    当 尝试获取分布式锁 "lock:expire" 超时 "1" 秒
    那么 返回结果应为 True
    并且 原始键 ":test:lock:expire" 应存在
