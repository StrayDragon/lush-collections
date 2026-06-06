# language: zh-CN
功能: 缓存策略 (cache_get_or_set)
  测试 AsyncRedisPrefixedOp 的缓存相关功能: 基本缓存命中、不缓存 None、缓存 None、强制刷新、TTL 过期

  场景: 基本缓存命中
    假设 已使用 prefixed 操作 ":test:"
    并且 Redis 键 ":test:cache:basic" 不存在
    当 调用 cache_get_or_set 键 "cache:basic" 使用生产者返回 "value1" 且 TTL 为 300 秒
    那么 返回的值应为 "value1"
    并且 生产者应调用了 "1" 次
    并且 原始键 ":test:cache:basic" 应存在
    当 再次调用 cache_get_or_set 键 "cache:basic" 使用生产者返回 "value2" 且 TTL 为 300 秒
    那么 返回的值应为 "value1"
    并且 生产者应调用了 "1" 次

  场景: 不缓存 None (SkipNone)
    假设 已使用 prefixed 操作 ":test:"
    并且 Redis 键 ":test:cache:skipnone" 不存在
    当 调用 cache_get_or_set 键 "cache:skipnone" 使用生产者返回 None 且不缓存 None
    那么 返回结果应为 None
    并且 生产者应调用了 "1" 次
    当 调用 cache_get_or_set 键 "cache:skipnone" 使用生产者返回 None 且不缓存 None
    那么 返回结果应为 None
    并且 生产者应调用了 "2" 次

  场景: 缓存 None (CacheAll)
    假设 已使用 prefixed 操作 ":test:"
    并且 Redis 键 ":test:cache:cachenone" 不存在
    当 调用 cache_get_or_set 键 "cache:cachenone" 使用生产者返回 None 且缓存 None
    那么 返回结果应为 None
    并且 生产者应调用了 "1" 次
    当 调用 cache_get_or_set 键 "cache:cachenone" 使用生产者返回 None 且缓存 None
    那么 返回结果应为 None
    并且 生产者应调用了 "1" 次

  场景: 强制调用生产者
    假设 已使用 prefixed 操作 ":test:"
    并且 Redis 键 ":test:cache:force" 不存在
    当 调用 cache_get_or_set 键 "cache:force" 使用生产者返回 "v1" 且 TTL 为 300 秒
    那么 返回的值应为 "v1"
    并且 生产者应调用了 "1" 次
    当 调用 cache_get_or_set 键 "cache:force" 使用生产者返回 "v2" 且强制调用生产者
    那么 返回的值应为 "v2"
    并且 生产者应调用了 "2" 次

  场景: 缓存 TTL 过期
    假设 已使用 prefixed 操作 ":test:"
    并且 Redis 键 ":test:cache:ttl" 不存在
    当 调用 cache_get_or_set 键 "cache:ttl" 使用生产者返回 "v1" 且 TTL 为 1 秒
    那么 返回的值应为 "v1"
    并且 生产者应调用了 "1" 次
    当 等待 "1.200000" 秒
    当 再次调用 cache_get_or_set 键 "cache:ttl" 使用生产者返回 "v2" 且 TTL 为 1 秒
    那么 返回的值应为 "v2"
    并且 生产者应调用了 "2" 次

  场景: None 使用短 TTL
    假设 已使用 prefixed 操作 ":test:"
    并且 Redis 键 ":test:cache:ttlnone" 不存在
    当 调用 cache_get_or_set 键 "cache:ttlnone" 使用生产者返回 None 且 None 使用短 TTL
    那么 返回结果应为 None
    并且 生产者应调用了 "1" 次
    当 等待 "1.200000" 秒
    当 调用 cache_get_or_set 键 "cache:ttlnone" 使用生产者返回 None 且 None 使用短 TTL
    那么 返回结果应为 None
    并且 生产者应调用了 "2" 次
