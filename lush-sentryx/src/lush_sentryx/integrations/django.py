# lush_sentryx/integrations/django.py
"""Sentryx Django 集成

提供 Django 框架的 Sentry 初始化工厂函数.

官方文档: https://docs.sentry.io/platforms/python/integrations/django/
"""

from __future__ import annotations

import logging
from typing import Any

from sentry_sdk.integrations import Integration
from typing_extensions import TypedDict, override

from lush_sentryx.core import SentryConfig, SentryManager

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TypedDict for type-safe overrides
# ---------------------------------------------------------------------------


class DjangoIntegrationOptions(TypedDict, total=False):
    """DjangoIntegration 参数类型定义

    所有字段均为可选.未指定的字段将使用 SDK 默认值.

    Attributes:
        transaction_style: 事务命名风格
            - "url": 使用 URL 路径 (如 "/myproject/myview/<foo>")
            - "function_name": 使用视图函数名 (如 "myproject.myview")
            SDK 默认值: "url"

        middleware_spans: 是否为中间件创建性能追踪 spans
            Tip: 启用会增加性能开销,仅在需要调试中间件性能时开启
            SDK 默认值: False

        signals_spans: 是否为 Django signals 创建性能追踪 spans
            Tip: 仅追踪同步 receiver 函数
            SDK 默认值: True

        signals_denylist: 排除性能追踪的信号列表
            Example: [django.db.models.signals.pre_init, ...]
            SDK 默认值: []

        cache_spans: 是否为缓存操作创建性能追踪 spans
            包含 hit/miss 信息
            SDK 默认值: False

        http_methods_to_capture: 需要创建事务的 HTTP 方法元组
            注意: OPTIONS 和 HEAD 默认不包含
            SDK 默认值: ("CONNECT", "DELETE", "GET", "PATCH", "POST", "PUT", "TRACE")
    """

    transaction_style: str
    middleware_spans: bool
    signals_spans: bool
    signals_denylist: list[Any]
    cache_spans: bool
    http_methods_to_capture: tuple[str, ...]


# ---------------------------------------------------------------------------
# Default Integration Factory
# ---------------------------------------------------------------------------


def default_django_integration(overrides: DjangoIntegrationOptions | None = None) -> Integration:
    """创建 DjangoIntegration,应用推荐配置

    使用此工厂函数创建 Integration,而非手动构建.
    这样可以确保使用最佳实践配置,同时保持对 SDK 新参数的即时支持.

    设计原则:
        - 只设置与 SDK 默认值不同的推荐配置
        - 其他参数让 SDK 自行处理默认值
        - 用户 overrides 优先级最高

    推荐配置 (本工厂函数应用的):
        - signals_spans=False: 关闭信号追踪以减少性能开销

    Args:
        overrides: 覆盖参数,使用 DjangoIntegrationOptions 类型获得类型提示

    Returns:
        DjangoIntegration 实例

    Tip (来自官方文档):
        - 如果使用 uWSGI,需要启用 --enable-threads 和 --py-call-uwsgi-fork-hooks
        - 设置 send_default_pii=True 时会自动附加用户信息 (id, email, username)

    Example:
        >>> # 使用默认推荐配置
        >>> integration = default_django_integration()
        >>>
        >>> # 启用中间件和缓存追踪
        >>> integration = default_django_integration(
        ...     {
        ...         "middleware_spans": True,
        ...         "cache_spans": True,
        ...     }
        ... )
        >>>
        >>> # SDK 新参数直接可用 (通过类型转换)
        >>> from typing import cast, Any
        >>> integration = default_django_integration(
        ...     cast(
        ...         DjangoIntegrationOptions,
        ...         {
        ...             "some_new_sdk_param": "value",
        ...         },
        ...     )
        ... )

    See Also:
        https://docs.sentry.io/platforms/python/integrations/django/#options
    """
    from sentry_sdk.integrations.django import DjangoIntegration

    # 只设置与 SDK 默认值不同的推荐配置
    # SDK 默认: signals_spans=True, 我们推荐关闭以减少性能开销
    params: dict[str, Any] = {
        "signals_spans": False,
    }

    # 合并用户 overrides
    if overrides:
        params.update(overrides)

    return DjangoIntegration(**params)


# endregion


class DjangoSentryConfig(SentryConfig):
    """Django Sentry 配置

    Example:
        基础使用:
            >>> config = DjangoSentryConfig(dsn="...", service_name="my-service")
            >>> config.init()  # 简单初始化

        使用 SentryManager:
            >>> config = DjangoSentryConfig(dsn="...", service_name="my-service")
            >>> manager = config.create_manager()
            >>> if manager.init():
            ...     manager.capture_message("Django service started")

        启用中间件 span:
            >>> config = DjangoSentryConfig(dsn="...", middleware_spans=True)

        自定义 HTTP 方法捕获:
            >>> config = DjangoSentryConfig(
            ...     dsn="...",
            ...     http_methods_to_capture=("GET", "POST", "PUT", "DELETE"),
            ... )

        排除特定信号的性能追踪:
            >>> from django.db.models.signals import pre_save
            >>> config = DjangoSentryConfig(
            ...     dsn="...",
            ...     signals_spans=True,
            ...     signals_denylist=[pre_save],
            ... )

        自定义 Redis 集成:
            >>> from sentry_sdk.integrations.redis import RedisIntegration
            >>> config = DjangoSentryConfig(
            ...     dsn="...",
            ...     redis_integration=lambda: RedisIntegration(max_data_size=1024),
            ... )
    """

    __slots__ = (
        "cache_spans",
        "http_methods_to_capture",
        "middleware_spans",
        "signals_denylist",
        "signals_spans",
        "transaction_style",
    )

    transaction_style: str
    """事务命名风格 ("url" 或 "function_name")"""

    middleware_spans: bool
    """是否为中间件创建 span"""

    signals_spans: bool
    """是否为 Django signals 创建 span"""

    signals_denylist: list[Any]
    """排除性能追踪的信号列表"""

    cache_spans: bool
    """是否为缓存操作创建 span"""

    http_methods_to_capture: tuple[str, ...]
    """需要创建事务的 HTTP 方法元组"""

    def __init__(
        self,
        *,
        # Django 特有参数
        transaction_style: str = "url",
        middleware_spans: bool = False,
        signals_spans: bool = False,
        signals_denylist: list[Any] | None = None,
        cache_spans: bool = False,
        http_methods_to_capture: tuple[str, ...] = (
            "CONNECT",
            "DELETE",
            "GET",
            "PATCH",
            "POST",
            "PUT",
            "TRACE",
        ),
        # 覆盖默认服务名
        service_name: str = "django-service",
        # 其他基类参数
        **kwargs: Any,
    ) -> None:
        super().__init__(service_name=service_name, **kwargs)
        self.transaction_style = transaction_style
        self.middleware_spans = middleware_spans
        self.signals_spans = signals_spans
        self.signals_denylist = signals_denylist if signals_denylist is not None else []
        self.cache_spans = cache_spans
        self.http_methods_to_capture = http_methods_to_capture

    @override
    def collect_integrations(self) -> list[Integration]:
        """收集 Django 相关的 Integration 列表"""
        try:
            from sentry_sdk.integrations.django import DjangoIntegration
        except (ImportError, Exception) as e:
            raise ImportError("Django integration requires 'django'. Install: pip install lush-sentryx[django]") from e

        integrations: list[Integration] = [
            DjangoIntegration(
                transaction_style=self.transaction_style,
                middleware_spans=self.middleware_spans,
                signals_spans=self.signals_spans,
                signals_denylist=self.signals_denylist,
                cache_spans=self.cache_spans,
                http_methods_to_capture=self.http_methods_to_capture,
            )
        ]

        integrations.extend(super().collect_integrations())
        return integrations


def init_sentry_for_django(cfg: DjangoSentryConfig) -> bool:
    """Django 项目 Sentry 初始化(简化版)

    需要安装: pip install lush-sentryx[django]

    Args:
        cfg: DjangoSentryConfig 配置对象

    Returns:
        初始化是否成功

    Example:
        >>> from lush_sentryx.integrations.django import init_sentry_for_django, DjangoSentryConfig
        >>>
        >>> # 基础使用
        >>> config = DjangoSentryConfig(dsn="...", service_name="my-service")
        >>> init_sentry_for_django(config)
        >>>
        >>> # 启用中间件和信号 span
        >>> config = DjangoSentryConfig(
        ...     dsn="...",
        ...     middleware_spans=True,
        ...     signals_spans=True,
        ... )
        >>> init_sentry_for_django(config)
        >>>
        >>> # 传递额外的 sentry_sdk.init() 参数
        >>> config = DjangoSentryConfig(
        ...     dsn="...",
        ...     extra_sentry_sdk_init_kwargs={"debug": True, "release": "1.0.0"},
        ... )
        >>> init_sentry_for_django(config)
    """
    return cfg.init()


def create_sentry_manager_for_django(cfg: DjangoSentryConfig) -> SentryManager:
    """创建 Django 项目的 SentryManager 实例

    SentryManager 提供更丰富的功能,包括:
    - capture_exception: 捕获异常并发送到 Sentry
    - capture_message: 发送消息到 Sentry
    - set_user_context: 设置用户上下文
    - add_breadcrumb: 添加面包屑
    - check_connection: 检查 Sentry 连接状态

    需要安装: pip install lush-sentryx[django]

    Args:
        cfg: DjangoSentryConfig 配置对象

    Returns:
        SentryManager 实例(未初始化,需要调用 manager.init())

    Example:
        >>> from lush_sentryx.integrations.django import create_sentry_manager_for_django, DjangoSentryConfig
        >>>
        >>> # 创建并初始化 manager
        >>> config = DjangoSentryConfig(dsn="...", service_name="my-service")
        >>> manager = create_sentry_manager_for_django(config)
        >>> if manager.init():
        ...     manager.capture_message("Django service started")
        >>>
        >>> # 在视图中使用
        >>> try:
        ...     process_request()
        ... except Exception as e:
        ...     manager.capture_exception(e, extras={"view": "user_detail"})
        >>>
        >>> # 使用自定义 logger
        >>> import logging
        >>> config = DjangoSentryConfig(dsn="...", logger=logging.getLogger("my_app"))
        >>> manager = create_sentry_manager_for_django(config)
    """
    return cfg.create_manager()
