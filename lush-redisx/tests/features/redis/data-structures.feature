# language: zh-CN
功能: 数据结构和批量操作
  测试 AsyncRedisPrefixedOp 的 hash、list、set、mget、mset 操作

  场景: 哈希设置和获取
    假设 已使用 prefixed 操作 ":test:"
    当 哈希设置键 "h:1" 字段 "f" 值为 "val"
    当 哈希获取键 "h:1" 字段 "f"
    那么 返回的值应为 "val"

  场景: 列表添加和批量获取
    假设 已使用 prefixed 操作 ":test:"
    当 列表右推键 "l:1" 值 "a"
    当 列表右推键 "l:1" 值 "b"
    当 列表右推键 "l:1" 值 "c"
    那么 原始键 ":test:l:1" 应存在

  场景: 集合添加和获取
    假设 已使用 prefixed 操作 ":test:"
    当 集合添加键 "s:1" 值 "x"
    当 集合添加键 "s:1" 值 "y"
    当 集合获取键 "s:1" 所有成员
    那么 返回值的类型应为 "set"

  场景: 批量获取
    假设 已使用 prefixed 操作 ":test:"
    当 设置键 "mg1" 值为 "v1"
    当 设置键 "mg2" 值为 "v2"
    当 批量获取键 "mg1" 和 "mg2"
    那么 返回值的类型应为 "list"

  场景: 批量设置
    假设 已使用 prefixed 操作 ":test:"
    当 批量设置键值: "ms1" = "a1", "ms2" = "a2"
    那么 返回结果应为 True
    并且 原始键 ":test:ms1" 应存在
    并且 原始键 ":test:ms1" 的值应为 "a1"
    并且 原始键 ":test:ms2" 应存在
    并且 原始键 ":test:ms2" 的值应为 "a2"
