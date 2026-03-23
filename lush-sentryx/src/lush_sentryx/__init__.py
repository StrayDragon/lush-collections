"""Sentryx - 独立的 Sentry 错误追踪集成库

一套围绕 sentry-sdk 的轻量封装: 配置集中、默认脱敏、可选集成,并尽量把失败当成“可降级事件”处理.

主要特性:
    - 类实例化模式,支持多实例
    - 纯 Python 配置对象,类型安全,无外部依赖
    - 默认的敏感字段过滤,并支持追加 denylist
    - 多框架集成支持 (FastAPI, Flask, Django 等)
    - 完整的健康检查和监控功能
    - 离线脚本和定时任务支持
    - 默认 Integration 工厂函数,开箱即用且可覆盖

Example:
    推荐用法 (使用默认 Integration 工厂函数):
        >>> from lush_sentryx import SentryConfig, SentryManager
        >>> from lush_sentryx.integrations.fastapi import default_fastapi_integrations
        >>> from lush_sentryx.integrations.common import default_common_integrations
        >>>
        >>> config = SentryConfig(
        ...     dsn="https://xxx@sentry.io/123",
        ...     environment="production",
        ...     integrations=[
        ...         *default_fastapi_integrations(),
        ...         *default_common_integrations(),
        ...     ],
        ... )
        >>> manager = config.create_manager()
        >>> manager.init()

    自定义 Integration 参数:
        >>> from lush_sentryx.integrations.fastapi import default_fastapi_integrations
        >>> from lush_sentryx.integrations.common import default_common_integrations
        >>>
        >>> config = SentryConfig(
        ...     dsn="...",
        ...     integrations=[
        ...         *default_fastapi_integrations(
        ...             transaction_style="endpoint",
        ...             failed_request_status_codes={500, 502, 503},
        ...         ),
        ...         *default_common_integrations(enable_redis=False),
        ...     ],
        ... )

    完全控制 (直接使用官方 Integration):
        >>> from sentry_sdk.integrations.fastapi import FastApiIntegration
        >>> from sentry_sdk.integrations.starlette import StarletteIntegration
        >>>
        >>> config = SentryConfig(
        ...     dsn="...",
        ...     integrations=[
        ...         StarletteIntegration(transaction_style="endpoint"),
        ...         FastApiIntegration(transaction_style="endpoint"),
        ...     ],
        ... )

    向后兼容 (使用框架特定 Config 类):
        >>> from lush_sentryx.integrations.fastapi import FastAPISentryConfig
        >>> config = FastAPISentryConfig(dsn="...", service_name="my-service")
        >>> config.init()

    链式钩子:
        >>> from lush_sentryx import chain_before_send
        >>> combined_hook = chain_before_send(base_hook, extra_hook)
"""

from lush_sentryx.core import SentryConfig, SentryManager, chain_before_send

__all__ = [
    "SentryConfig",
    "SentryManager",
    "chain_before_send",
]
