"""Sentryx Core SDK v2 类型定义

定义与 Sentry SDK 2.x 兼容的类型别名.

类型导入策略:
    - 类型检查时 (TYPE_CHECKING=True): 从 sentry-sdk 导入原生类型,获得完整的类型检查
    - 运行时: 使用本模块定义的类型别名,无需依赖 sentry-sdk

这样设计的好处:
    1. 类型检查器能获得与 sentry-sdk 完全匹配的类型定义
    2. 运行时不强制依赖 sentry-sdk,保持核心库的独立性
    3. 传递给 sentry_sdk.init() 的回调函数类型完全兼容

使用示例:
    >>> from lush_sentryx_core.sdk.v2.types import Event, Hint
    >>> def my_filter(event: Event, hint: Hint) -> Event | None:
    ...     return event

Note:
    - 需要在环境中安装 sentry-sdk>=2.0.0 才能获得正确的类型检查
    - 运行时这些类型是 Any 的别名,不会影响代码执行
"""

from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from collections.abc import Callable

    from sentry_sdk._types import (
        Breadcrumb as SentryBreadcrumb,
    )
    from sentry_sdk._types import (
        Event as SentryEvent,
    )
    from sentry_sdk._types import (
        EventProcessor as SentryEventProcessor,
    )
    from sentry_sdk._types import (
        ExcInfo as SentryExcInfo,
    )
    from sentry_sdk._types import (
        Hint as SentryHint,
    )
    from sentry_sdk._types import (
        TransactionProcessor as SentryTransactionProcessor,
    )
else:
    from collections.abc import Callable

# region 基础类型别名

SensitiveFields = set[str] | frozenset[str]
"""敏感字段集合类型"""

# endregion


# region 条件类型导出 (TYPE_CHECKING 时使用 sentry-sdk 原生类型)

if TYPE_CHECKING:
    # 类型检查时: 使用 sentry-sdk 原生类型
    # 这确保 create_additional_filter 等函数返回的类型与
    # sentry_sdk.init(before_send=...) 期望的类型完全匹配
    Event = SentryEvent
    Hint = SentryHint
    ExcInfo = SentryExcInfo
    Breadcrumb = SentryBreadcrumb
    EventProcessor = SentryEventProcessor
    TransactionProcessor = SentryTransactionProcessor
else:
    # 运行时: 使用 Any 别名,不需要 sentry-sdk 依赖
    Event = dict[str, Any]
    Hint = dict[str, Any]
    ExcInfo = tuple[type[BaseException], BaseException, Any] | tuple[None, None, None]
    Breadcrumb = dict[str, Any]
    EventProcessor = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any] | None]
    TransactionProcessor = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any] | None]

# endregion


# region 内部辅助类型 (用于 utils.py 等模块的类型注解)


class Request(TypedDict, total=False):
    """请求数据结构"""

    url: str
    method: str
    query_string: str
    data: dict[str, Any] | str
    cookies: dict[str, str]
    headers: dict[str, str]
    env: dict[str, str]


class User(TypedDict, total=False):
    """用户数据结构"""

    id: str
    username: str
    email: str
    ip_address: str
    name: str
    geo: dict[str, Any]
    data: dict[str, Any]


# endregion
