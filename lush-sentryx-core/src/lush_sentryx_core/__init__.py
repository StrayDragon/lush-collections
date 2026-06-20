"""Sentryx Core - Sentry 敏感数据过滤核心库

这是一个独立的敏感数据过滤和脱敏核心库,不依赖 sentry-sdk.
可被任何版本的 Sentry SDK (1.x 或 2.x) 使用,也可独立用于其他数据脱敏场景.

主要特性:
    - 纯 Python 实现,无外部依赖
    - 深度递归清理嵌套数据结构
    - 支持自定义敏感字段列表
    - 提供 URL 参数清理、邮箱脱敏等工具函数
    - 兼容 Sentry SDK 1.x 和 2.x 的事件结构
    - 提供类型定义用于类型检查

使用方式:

    1. 推荐方式 - 通过版本命名空间导入 (明确 SDK 版本):
        >>> from lush_sentryx_core.sdk.v2 import create_additional_filter, SENTRY_DEFAULT_DENYLIST
        >>> from lush_sentryx_core.sdk.v2.types import Event, Hint

    2. 简化方式 - 直接导入 (默认使用 v2):
        >>> from lush_sentryx_core import create_additional_filter, SENTRY_DEFAULT_DENYLIST

    3. 独立使用 (数据脱敏):
        >>> from lush_sentryx_core import deep_scrub_sensitive_data, SENTRY_DEFAULT_DENYLIST
        >>> data = {"password": "secret", "config": {"token": "xxx"}}
        >>> deep_scrub_sensitive_data(data, SENTRY_DEFAULT_DENYLIST)
        >>> data
        {'password': '[Filtered]', 'config': {'token': '[Filtered]'}}

    4. 配合 Sentry SDK 使用:
        >>> from lush_sentryx_core.sdk.v2 import create_additional_filter, SENTRY_DEFAULT_DENYLIST
        >>> import sentry_sdk
        >>> sentry_sdk.init(
        ...     dsn="...",
        ...     before_send=create_additional_filter(SENTRY_DEFAULT_DENYLIST),
        ... )

Note:
    - 当前默认导出的是 SDK v2 版本的实现
    - 如果需要支持 SDK 1.x,可以在 sdk 目录下添加 v1 模块
"""

# 导入 sdk 命名空间
from lush_sentryx_core import sdk

# 从 v2 重新导出常用 API (保持向后兼容)
from lush_sentryx_core.sdk.v2 import (
    # 常量
    FILTERED_PLACEHOLDER,
    SENSITIVE_URL_PATTERNS,
    SENTRY_DEFAULT_DENYLIST,
    # 类型 (类型检查时使用 sentry-sdk 原生类型)
    Breadcrumb,
    Event,
    EventProcessor,
    ExcInfo,
    Hint,
    SensitiveFields,
    TransactionProcessor,
    # 过滤器工厂 (返回 EventProcessor/TransactionProcessor 类型)
    create_additional_filter,
    create_transaction_filter,
    # 工具函数
    custom_repr,
    # 数据清理函数
    deep_scrub_sensitive_data,
    mask_email_partially,
    mask_string_partially,
    mask_user_email_partially,
    parameterize_request_urls,
    scrub_dict_keys,
    scrub_stacktrace_vars,
)

__all__ = [  # noqa: RUF022
    # SDK 命名空间
    "sdk",
    # 类型 (类型检查时使用 sentry-sdk 原生类型,确保与 sentry_sdk.init() 完全兼容)
    "Breadcrumb",
    "Event",
    "EventProcessor",
    "ExcInfo",
    "Hint",
    "SensitiveFields",
    "TransactionProcessor",
    # 常量
    "FILTERED_PLACEHOLDER",
    "SENSITIVE_URL_PATTERNS",
    "SENTRY_DEFAULT_DENYLIST",
    # 过滤器工厂 (返回 EventProcessor/TransactionProcessor 类型)
    "create_additional_filter",
    "create_transaction_filter",
    # 数据清理函数
    "deep_scrub_sensitive_data",
    "scrub_dict_keys",
    "scrub_stacktrace_vars",
    # 工具函数
    "custom_repr",
    "mask_email_partially",
    "mask_string_partially",
    "mask_user_email_partially",
    "parameterize_request_urls",
]
