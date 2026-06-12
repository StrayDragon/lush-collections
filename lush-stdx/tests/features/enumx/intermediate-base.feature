# language: zh-CN

功能: 应用级中间基类
  作为库使用者
  我希望定义一次中间基类覆盖 x_meta 返回类型
  使得所有业务枚举无需重复声明 property override

  背景:
    假设 枚举测试 fixture 已就绪

  场景: 通过中间基类统一扩展 XMetaInfo
    假设 存在通过中间基类定义的 IntEnum 子类 "order_status"
    那么 "order_status" 成员 PENDING 的 x_meta badge 是 "⏳"
    并且 "order_status" 成员 PENDING 的 x_meta css_class 是 "label-warning"
    并且 "order_status" 成员 SHIPPED 的 x_meta description 是 "已发货"
    并且 "order_status" 成员 SHIPPED 的 x_meta badge 是 "📦"
    并且 "order_status" 成员 PENDING 的 value 是 1
    并且 "order_status" 成员 SHIPPED 的 value 是 2

  场景: 多个业务枚举共享同一个中间基类
    假设 存在通过中间基类定义的 IntEnum 子类 "order_status"
    并且 存在通过中间基类定义的 IntEnum 子类 "payment_method"
    那么 "payment_method" 成员 WECHAT 的 x_meta badge 是 "💚"
    并且 "payment_method" 成员 ALIPAY 的 x_meta css_class 是 "label-blue"
    并且 "order_status" 成员 PENDING 的 x_meta css_class 是 "label-warning"
