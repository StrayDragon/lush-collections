"""Sentryx 框架集成模块

提供与各种 Web 框架的集成支持.

每个框架集成模块都提供:
    1. 默认 Integration 工厂函数 (推荐) - 直接创建 Integration 实例
    2. 框架特定 Config 类 (向后兼容) - 封装配置和初始化逻辑

可用模块:
    - lush_sentryx.integrations.fastapi: FastAPI 集成
        - default_fastapi_integrations(): 创建 StarletteIntegration + FastApiIntegration
    - lush_sentryx.integrations.flask: Flask 集成
        - default_flask_integration(): 创建 FlaskIntegration
    - lush_sentryx.integrations.django: Django 集成
        - default_django_integration(): 创建 DjangoIntegration
    - lush_sentryx.integrations.common: 通用集成
        - default_common_integrations(): 创建 SQLAlchemy + Redis + Logging 集成
        - default_sqlalchemy_integration(): 创建 SqlalchemyIntegration
        - default_redis_integration(): 创建 RedisIntegration
        - default_logging_integration(): 创建 LoggingIntegration

推荐方式 (使用默认 Integration 工厂函数):
    >>> from lush_sentryx import SentryConfig
    >>> from lush_sentryx.integrations.fastapi import default_fastapi_integrations
    >>> from lush_sentryx.integrations.common import default_common_integrations
    >>>
    >>> config = SentryConfig(
    ...     dsn="...",
    ...     integrations=[
    ...         *default_fastapi_integrations(transaction_style="endpoint"),
    ...         *default_common_integrations(),
    ...     ],
    ... )
    >>> manager = config.create_manager()
    >>> manager.init()

向后兼容方式 (框架特定 Config 类):
    每个框架集成提供两种初始化方式:
    1. `init_sentry_for_xxx()` - 简单初始化,返回 bool
    2. `create_sentry_manager_for_xxx()` - 返回 SentryManager 实例

    FastAPI:
        >>> from lush_sentryx.integrations.fastapi import FastAPISentryConfig
        >>> config = FastAPISentryConfig(dsn="...", service_name="my-service")
        >>> config.init()

    Flask:
        >>> from lush_sentryx.integrations.flask import FlaskSentryConfig
        >>> config = FlaskSentryConfig(dsn="...", service_name="my-service")
        >>> config.init()

    Django:
        >>> from lush_sentryx.integrations.django import DjangoSentryConfig
        >>> config = DjangoSentryConfig(dsn="...", service_name="my-service")
        >>> config.init()
"""
