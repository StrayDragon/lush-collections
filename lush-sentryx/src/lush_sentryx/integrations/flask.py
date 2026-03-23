# lush_sentryx/integrations/flask.py
"""Sentryx Flask 集成

提供 Flask 框架的 Sentry 初始化工厂函数.

官方文档: https://docs.sentry.io/platforms/python/integrations/flask/
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sentry_sdk.integrations import Integration
from typing_extensions import TypedDict, override

from lush_sentryx.core import SentryConfig, SentryManager, default_sqlalchemy_integration

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TypedDict for type-safe overrides
# ---------------------------------------------------------------------------


class FlaskIntegrationOptions(TypedDict, total=False):
    """FlaskIntegration 参数类型定义

    所有字段均为可选.未指定的字段将使用 SDK 默认值.

    Attributes:
        transaction_style: 事务命名风格
            - "url": 使用 URL 路径 (如 "/myurl/<foo>")
            - "endpoint": 使用端点名称 (如 "myendpoint")
            SDK 默认值: "endpoint"

        http_methods_to_capture: 需要创建事务的 HTTP 方法元组
            注意: OPTIONS 和 HEAD 默认不包含
            SDK 默认值: ("CONNECT", "DELETE", "GET", "PATCH", "POST", "PUT", "TRACE")
    """

    transaction_style: str
    http_methods_to_capture: tuple[str, ...]


class FlaskSentryConfig(SentryConfig):
    """Flask Sentry 配置

    Example:
        基础使用:
            >>> config = FlaskSentryConfig(dsn="...", service_name="my-service")
            >>> config.init()  # 简单初始化

        使用 SentryManager:
            >>> config = FlaskSentryConfig(dsn="...", service_name="my-service")
            >>> manager = config.create_manager()
            >>> if manager.init():
            ...     manager.capture_message("Flask service started")

        禁用 SQLAlchemy 集成:
            >>> config = FlaskSentryConfig(dsn="...", enable_sqlalchemy=False)

        自定义 HTTP 方法捕获:
            >>> config = FlaskSentryConfig(
            ...     dsn="...",
            ...     http_methods_to_capture=("GET", "POST", "PUT", "DELETE"),
            ... )

        自定义 SQLAlchemy 集成:
            >>> from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
            >>> config = FlaskSentryConfig(
            ...     dsn="...",
            ...     sqlalchemy_integration_factory=lambda: SqlalchemyIntegration(connect_timeout=10),
            ... )
    """

    __slots__ = (
        "enable_sqlalchemy",
        "http_methods_to_capture",
        "sqlalchemy_integration_factory",
        "transaction_style",
    )

    transaction_style: str
    """事务命名风格 ("url" 或 "endpoint")"""

    enable_sqlalchemy: bool
    """是否启用 SQLAlchemy 集成"""

    sqlalchemy_integration_factory: Callable[[], Integration] | None
    """SQLAlchemy 集成工厂函数"""

    http_methods_to_capture: tuple[str, ...]
    """需要创建事务的 HTTP 方法元组"""

    def __init__(
        self,
        *,
        # Flask 特有参数
        transaction_style: str = "url",
        enable_sqlalchemy: bool = True,
        sqlalchemy_integration_factory: Callable[[], Integration] | None = None,
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
        service_name: str = "flask-service",
        # 其他基类参数
        **kwargs: Any,
    ) -> None:
        super().__init__(service_name=service_name, **kwargs)
        self.transaction_style = transaction_style
        self.enable_sqlalchemy = enable_sqlalchemy
        self.sqlalchemy_integration_factory = sqlalchemy_integration_factory or default_sqlalchemy_integration
        self.http_methods_to_capture = http_methods_to_capture

    @override
    def collect_integrations(self) -> list[Integration]:
        """收集 Flask 相关的 Integration 列表"""
        try:
            from sentry_sdk.integrations.flask import FlaskIntegration
        except (ImportError, Exception) as e:
            raise ImportError("Flask integration requires 'flask'. Install: pip install lush-sentryx[flask]") from e

        integrations: list[Integration] = [
            FlaskIntegration(
                transaction_style=self.transaction_style,
                http_methods_to_capture=self.http_methods_to_capture,
            )
        ]

        if self.enable_sqlalchemy and self.sqlalchemy_integration_factory is not None:
            try:
                integrations.append(self.sqlalchemy_integration_factory())
            except (ImportError, Exception):
                _logger.debug("SQLAlchemy integration not available")

        integrations.extend(super().collect_integrations())
        return integrations


def init_sentry_for_flask(cfg: FlaskSentryConfig) -> bool:
    """Flask 项目 Sentry 初始化(简化版)

    需要安装: pip install lush-sentryx[flask]

    Args:
        cfg: FlaskSentryConfig 配置对象

    Returns:
        初始化是否成功

    Example:
        >>> from lush_sentryx.integrations.flask import init_sentry_for_flask, FlaskSentryConfig
        >>>
        >>> # 基础使用
        >>> config = FlaskSentryConfig(dsn="...", service_name="my-service")
        >>> init_sentry_for_flask(config)
        >>>
        >>> # 禁用 SQLAlchemy 集成
        >>> config = FlaskSentryConfig(dsn="...", enable_sqlalchemy=False)
        >>> init_sentry_for_flask(config)
        >>>
        >>> # 自定义 SQLAlchemy 集成
        >>> from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        >>> config = FlaskSentryConfig(
        ...     dsn="...",
        ...     sqlalchemy_integration_factory=lambda: SqlalchemyIntegration(connect_timeout=10),
        ... )
        >>> init_sentry_for_flask(config)
        >>>
        >>> # 传递额外的 sentry_sdk.init() 参数
        >>> config = FlaskSentryConfig(
        ...     dsn="...",
        ...     extra_sentry_sdk_init_kwargs={"debug": True, "release": "1.0.0"},
        ... )
        >>> init_sentry_for_flask(config)
    """
    return cfg.init()


def create_sentry_manager_for_flask(cfg: FlaskSentryConfig) -> SentryManager:
    """创建 Flask 项目的 SentryManager 实例

    SentryManager 提供更丰富的功能,包括:
    - capture_exception: 捕获异常并发送到 Sentry
    - capture_message: 发送消息到 Sentry
    - set_user_context: 设置用户上下文
    - add_breadcrumb: 添加面包屑
    - check_connection: 检查 Sentry 连接状态

    需要安装: pip install lush-sentryx[flask]

    Args:
        cfg: FlaskSentryConfig 配置对象

    Returns:
        SentryManager 实例(未初始化,需要调用 manager.init())

    Example:
        >>> from lush_sentryx.integrations.flask import create_sentry_manager_for_flask, FlaskSentryConfig
        >>>
        >>> # 创建并初始化 manager
        >>> config = FlaskSentryConfig(dsn="...", service_name="my-service")
        >>> manager = create_sentry_manager_for_flask(config)
        >>> if manager.init():
        ...     manager.capture_message("Flask service started")
        >>>
        >>> # 在异常处理中使用
        >>> try:
        ...     risky_operation()
        ... except Exception as e:
        ...     manager.capture_exception(e, extras={"context": "important"})
        >>>
        >>> # 使用自定义 logger
        >>> import logging
        >>> config = FlaskSentryConfig(dsn="...", logger=logging.getLogger("my_app"))
        >>> manager = create_sentry_manager_for_flask(config)
    """
    return cfg.create_manager()


# ---------------------------------------------------------------------------
# Default Integration Factory
# ---------------------------------------------------------------------------


def default_flask_integration(overrides: FlaskIntegrationOptions | None = None) -> Integration:
    """创建 FlaskIntegration,应用推荐配置

    使用此工厂函数创建 Integration,而非手动构建.
    这样可以确保使用最佳实践配置,同时保持对 SDK 新参数的即时支持.

    设计原则:
        - 不设置任何默认值,完全使用 SDK 默认值
        - 用户 overrides 优先级最高

    Args:
        overrides: 覆盖参数,使用 FlaskIntegrationOptions 类型获得类型提示

    Returns:
        FlaskIntegration 实例

    Tip (来自官方文档):
        - 如果使用 uWSGI,需要启用 --enable-threads 和 --py-call-uwsgi-fork-hooks
        - 使用 flask-login 并设置 send_default_pii=True 时会附加用户信息
        - Flask 集成会自动启用,无需显式添加

    Example:
        >>> # 使用 SDK 默认配置
        >>> integration = default_flask_integration()
        >>>
        >>> # 自定义事务命名风格
        >>> integration = default_flask_integration(
        ...     {
        ...         "transaction_style": "url",
        ...     }
        ... )
        >>>
        >>> # 限制捕获的 HTTP 方法
        >>> integration = default_flask_integration(
        ...     {
        ...         "http_methods_to_capture": ("GET", "POST"),
        ...     }
        ... )

    See Also:
        https://docs.sentry.io/platforms/python/integrations/flask/#options
    """
    try:
        from sentry_sdk.integrations.flask import FlaskIntegration
    except (ImportError, Exception) as e:
        raise ImportError("Flask integration requires 'flask'. Install: pip install lush-sentryx[flask]") from e

    # 不设置任何默认值,完全使用 SDK 默认值
    params: dict[str, Any] = {}

    # 合并用户 overrides
    if overrides:
        params.update(overrides)

    return FlaskIntegration(**params)
