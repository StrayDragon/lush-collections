# language: zh-CN

功能: MetaInfoEnum 基本继承
  作为库使用者
  我希望直接继承 MetaInfoIntEnum 或 MetaInfoStrEnum
  以便快速定义带有元信息的枚举

  背景:
    假设 枚举测试 fixture 已就绪

  场景: 继承 MetaInfoIntEnum 并访问基本属性
    假设 存在 MetaInfoIntEnum 子类 "basic_int"
    那么 "basic_int" 成员 PENDING 的 value 是 1
    并且 "basic_int" 成员 PENDING 的 x_meta description 是 "等待中"
    并且 "basic_int" 成员 PENDING 是 int 实例
    并且 "basic_int" 成员 PENDING 是自身枚举的实例
    并且 通过值 1 实例化 "basic_int" 得到成员 PENDING
    并且 "basic_int" 的成员总数是 2

  场景: 继承 MetaInfoStrEnum 并访问基本属性
    假设 存在 MetaInfoStrEnum 子类 "basic_str"
    那么 "basic_str" 成员 VANILLA 的 value 是 "vanilla"
    并且 "basic_str" 成员 VANILLA 的 x_meta description 是 "香草味"
    并且 str 表示 "basic_str" 成员 VANILLA 是 "vanilla"
    并且 "basic_str" 成员 VANILLA 是自身枚举的实例
    并且 "basic_str" 的成员总数是 2

  场景: to_db_field_comment 生成数据库注释
    假设 存在 MetaInfoIntEnum 子类 "priority"
    那么 "priority" 的 to_db_field_comment 包含 "0: 低优先级 1: 高优先级"

  场景: to_db_field_comment 不包含其他枚举的描述
    假设 存在 MetaInfoIntEnum 子类 "basic_int"
    那么 "basic_int" 的 to_db_field_comment 包含 "0: 低优先级 1: 高优先级" 是假
