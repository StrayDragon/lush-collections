# language: zh-CN
功能: 节流和防抖
  测试 AsyncRedisPrefixedOp 的 throttle_check_and_set、debounce_check_and_set、debounce_get_remaining

  场景: 首次节流允许通过
    假设 已使用 prefixed 操作 ":test:"
    并且 Redis 键 ":test:thr:first" 不存在
    当 节流检查键 "thr:first" 窗口 "10" 秒
    那么 返回结果为 DebounceResult 且 allowed 为 "true"

  场景: 窗口内第二次节流被拒绝
    假设 已使用 prefixed 操作 ":test:"
    并且 Redis 键 ":test:thr:again" 不存在
    当 节流检查键 "thr:again" 窗口 "10" 秒
    那么 返回结果为 DebounceResult 且 allowed 为 "true"
    当 节流检查键 "thr:again" 窗口 "10" 秒
    那么 返回结果为 DebounceResult 且 allowed 为 "false"
    并且 返回结果为 DebounceResult 且 remaining_seconds > "0"

  场景: 防抖窗口内第二次被拒绝
    假设 已使用 prefixed 操作 ":test:"
    并且 Redis 键 ":test:deb:again" 不存在
    当 防抖检查键 "deb:again" 窗口 "5" 秒
    那么 返回结果为 DebounceResult 且 allowed 为 "true"
    当 防抖检查键 "deb:again" 窗口 "5" 秒
    那么 返回结果为 DebounceResult 且 allowed 为 "false"

  场景: 防抖过期后重新允许
    假设 已使用 prefixed 操作 ":test:"
    并且 Redis 键 ":test:deb:expire" 不存在
    当 防抖检查键 "deb:expire" 窗口 "1" 秒
    那么 返回结果为 DebounceResult 且 allowed 为 "true"
    当 防抖检查键 "deb:expire" 窗口 "1" 秒
    那么 返回结果为 DebounceResult 且 allowed 为 "false"
    当 等待 "1.200000" 秒
    当 防抖检查键 "deb:expire" 窗口 "1" 秒
    那么 返回结果为 DebounceResult 且 allowed 为 "true"

  场景: 防抖查询不存在的键返回 allowed
    假设 已使用 prefixed 操作 ":test:"
    并且 Redis 键 ":test:deb:ghost" 不存在
    当 防抖查询剩余时间键 "deb:ghost"
    那么 返回结果为 DebounceResult 且 allowed 为 "true"

  场景: 防抖查询已存在的键返回正确剩余时间
    假设 已使用 prefixed 操作 ":test:"
    并且 Redis 键 ":test:deb:exist" 不存在
    当 防抖检查键 "deb:exist" 窗口 "10" 秒
    那么 返回结果为 DebounceResult 且 allowed 为 "true"
    当 防抖查询剩余时间键 "deb:exist"
    那么 返回结果为 DebounceResult 且 allowed 为 "false"
    并且 返回结果为 DebounceResult 且 remaining_seconds > "0"
