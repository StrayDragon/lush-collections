# language: zh-CN

功能: 扩展 XMetaInfo
  作为库使用者
  我希望扩展 XMetaInfo 添加自定义字段
  以便枚举成员携带业务元信息且类型检查器知晓

  背景:
    假设 枚举测试 fixture 已就绪

  场景: 扩展 XMetaInfo 添加 color 和 order 字段
    假设 存在带扩展 meta 的 IntEnum 子类 "extended_int"
    那么 "extended_int" 成员 RED 的 value 是 1
    并且 "extended_int" 成员 RED 的 x_meta color 是 "#ff0000"
    并且 "extended_int" 成员 RED 的 x_meta order 是 1
    并且 "extended_int" 成员 GREEN 的 x_meta description 是 "绿色"
    并且 "extended_int" 成员 GREEN 的 x_meta color 是 "#00ff00"

  场景: 扩展 XMetaInfo 用于 StrEnum 添加 icon 字段
    假设 存在带扩展 meta 的 StrEnum 子类 "extended_str"
    那么 "extended_str" 成员 SUCCESS 的 value 是 "success"
    并且 "extended_str" 成员 SUCCESS 的 x_meta icon 是 "✅"
    并且 "extended_str" 成员 WARNING 的 x_meta description 是 "警告"
