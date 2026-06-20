"""Sentryx Core SDK v2 - 适用于 Sentry SDK 2.x

此模块提供与 Sentry SDK 2.x 兼容的类型定义、过滤器和工具函数.

主要特性:
    - 类型定义: Event, Hint, Breadcrumb 等类型别名
    - 过滤器工厂: before_send, before_send_transaction 过滤器
    - 数据清理: 深度递归清理敏感数据
    - 工具函数: 邮箱脱敏、URL 清理等

Example:
    基本使用:
        >>> from lush_sentryx_core.sdk.v2 import create_additional_filter, SENTRY_DEFAULT_DENYLIST
        >>> import sentry_sdk
        >>> sentry_sdk.init(
        ...     dsn="...",
        ...     before_send=create_additional_filter(SENTRY_DEFAULT_DENYLIST),
        ... )

    类型提示:
        >>> from lush_sentryx_core.sdk.v2.types import Event, Hint
        >>> def my_filter(event: Event, hint: Hint) -> Event | None:
        ...     return event

Note:
    - 此模块不依赖 sentry-sdk,但类型定义与 sentry-sdk 2.x 兼容
    - 如果需要使用 sentry-sdk 的原生类型,可以在运行时导入
"""

from lush_sentryx_core.sdk.v2.const import (
    FILTERED_PLACEHOLDER,
    SENSITIVE_URL_PATTERNS,
    SENTRY_DEFAULT_DENYLIST,
)
from lush_sentryx_core.sdk.v2.filters import (
    create_additional_filter,
    create_transaction_filter,
)
from lush_sentryx_core.sdk.v2.scrubbers import (
    deep_scrub_sensitive_data,
    scrub_dict_keys,
    scrub_stacktrace_vars,
)
from lush_sentryx_core.sdk.v2.types import (
    Breadcrumb,
    Event,
    EventProcessor,
    ExcInfo,
    Hint,
    SensitiveFields,
    TransactionProcessor,
)
from lush_sentryx_core.sdk.v2.utils import (
    custom_repr,
    mask_email_partially,
    mask_string_partially,
    mask_user_email_partially,
    parameterize_request_urls,
)

__all__ = [  # noqa: RUF022
    # 类型 (类型检查时使用 sentry-sdk 原生类型)
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
