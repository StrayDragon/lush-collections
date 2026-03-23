"""Sentryx Core SDK v2 事件过滤器

提供事件的额外过滤和清理功能.
此模块不依赖 sentry-sdk, 可被任何 Sentry SDK 版本使用.

类型兼容性:
    - create_additional_filter 返回 EventProcessor 类型
    - create_transaction_filter 返回 TransactionProcessor 类型
    - 这两个类型在类型检查时与 sentry_sdk.init() 的参数类型完全匹配
"""

import re

from lush_sentryx_core.sdk.v2.const import SENSITIVE_URL_PATTERNS
from lush_sentryx_core.sdk.v2.scrubbers import deep_scrub_sensitive_data, scrub_stacktrace_vars
from lush_sentryx_core.sdk.v2.types import Event, EventProcessor, Hint, SensitiveFields, TransactionProcessor
from lush_sentryx_core.sdk.v2.utils import mask_user_email_partially, parameterize_request_urls


def create_additional_filter(
    sensitive_fields: SensitiveFields,
) -> EventProcessor:
    """创建轻量级事件过滤器,补充 EventScrubber 未覆盖的场景

    EventScrubber 已自动处理标准的敏感字段清理,这个过滤器处理:
    - URL 查询参数清理 (移除包含 token/key/secret 的查询参数)
    - 用户邮箱脱敏处理 (保留部分信息用于识别)
    - 深度递归清理嵌套数据结构 (extra, contexts 等)
    - 其他 EventScrubber 无法自动处理的场景

    Args:
        sensitive_fields: 敏感字段名的集合 (用于深度清理)

    Returns:
        callable: before_send 过滤器函数,签名为 (Event, Hint) -> Event | None

    Note:
        - 这是一个工厂函数,返回实际的过滤器函数
        - 兼容 Sentry SDK 2.x 的 before_send 回调

    Example:
        >>> from lush_sentryx_core.sdk.v2 import create_additional_filter, SENTRY_DEFAULT_DENYLIST
        >>> import sentry_sdk
        >>> sentry_sdk.init(
        ...     dsn="...",
        ...     before_send=create_additional_filter(SENTRY_DEFAULT_DENYLIST),
        ... )
    """

    def additional_filter(event: Event, hint: Hint) -> Event | None:  # noqa: ARG001  # pyright: ignore[reportUnusedParameter]
        """轻量级事件过滤器:处理 EventScrubber 未覆盖的场景"""
        try:
            # 1. 清理 URL 中的敏感查询参数
            request = event.get("request", {})
            if request:
                parameterize_request_urls(request)

            # 2. 用户邮箱脱敏处理 (保留部分信息用于识别)
            user = event.get("user", {})
            if user:
                mask_user_email_partially(user)

            # 3. 深度清理 extra 数据 (补充 EventScrubber 的清理)
            if "extra" in event:
                deep_scrub_sensitive_data(event["extra"], sensitive_fields)

            # 4. 深度清理 contexts 数据
            if "contexts" in event:
                deep_scrub_sensitive_data(event["contexts"], sensitive_fields)

            # 5. 深度清理堆栈帧中的局部变量 (EventScrubber 不能递归处理嵌套对象)
            scrub_stacktrace_vars(event, sensitive_fields)

        except Exception:
            # 出现异常时返回None,避免发送可能包含敏感数据的事件
            return None
        else:
            return event

    return additional_filter


def create_transaction_filter() -> TransactionProcessor:
    """创建事务名称过滤器, 防止事务名称中包含敏感信息

    Returns:
        callable: before_send_transaction 过滤器函数,签名为 (Event, Hint) -> Event | None

    Note:
        - 这是一个工厂函数,返回实际的过滤器函数
        - 兼容 Sentry SDK 2.x 的 before_send_transaction 回调

    Example:
        >>> from lush_sentryx_core.sdk.v2 import create_transaction_filter
        >>> import sentry_sdk
        >>> sentry_sdk.init(
        ...     dsn="...",
        ...     before_send_transaction=create_transaction_filter(),
        ... )
    """

    def transaction_filter(event: Event, hint: Hint) -> Event | None:  # noqa: ARG001  # pyright: ignore[reportUnusedParameter]
        """过滤事务名称中的敏感信息"""
        try:
            transaction_name = event.get("transaction")
            if transaction_name and isinstance(transaction_name, str):
                for pattern in SENSITIVE_URL_PATTERNS:
                    if pattern.search(transaction_name):
                        transaction_name = re.sub(
                            r"[\?&](?:token|key|secret|password|api_key)=[\w\-\.]+",
                            r"?[Filtered]",
                            transaction_name,
                            flags=re.IGNORECASE,
                        )
                        event["transaction"] = transaction_name
                        break

        except Exception:
            return event
        else:
            return event

    return transaction_filter
