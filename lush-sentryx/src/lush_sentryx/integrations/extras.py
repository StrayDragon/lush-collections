# lush_sentryx/integrations/extras.py
"""Sentryx 通用集成

提供通用的集成工厂函数,可与任何框架组合使用.
包含 SQLAlchemy、Redis、Logging 等通用集成.

官方文档:
    - SQLAlchemy: https://docs.sentry.io/platforms/python/integrations/sqlalchemy/
    - Redis: https://docs.sentry.io/platforms/python/integrations/redis/
    - Logging: https://docs.sentry.io/platforms/python/integrations/logging/
"""

from __future__ import annotations

import logging
from typing import Any

from sentry_sdk.integrations import Integration
from typing_extensions import TypedDict

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TypedDict for type-safe options
# ---------------------------------------------------------------------------


class SqlalchemyIntegrationOptions(TypedDict, total=False):
    """SqlalchemyIntegration 参数类型定义

    所有字段均为可选.未指定的字段将使用 SDK 默认值.

    Note:
        SQLAlchemy 集成会自动启用,如果检测到 sqlalchemy 包.
        主要用于追踪数据库查询性能.
    """

    # 目前 SqlalchemyIntegration 没有公开配置参数
    # 预留此 TypedDict 以便未来 SDK 添加参数时使用


class RedisIntegrationOptions(TypedDict, total=False):
    """RedisIntegration 参数类型定义

    所有字段均为可选.未指定的字段将使用 SDK 默认值.

    Attributes:
        max_data_size: 捕获的 Redis 命令数据的最大大小(字节)
            超过此大小的数据将被截断
            SDK 默认值: 1024
    """

    max_data_size: int


class LoggingIntegrationOptions(TypedDict, total=False):
    """LoggingIntegration 参数类型定义

    所有字段均为可选.未指定的字段将使用 SDK 默认值.

    Attributes:
        level: 记录为面包屑的最低日志级别
            SDK 默认值: logging.INFO (20)

        event_level: 作为事件发送的最低日志级别
            设置为 None 禁用将日志作为事件发送
            SDK 默认值: logging.ERROR (40)
    """

    level: int
    event_level: int | None


def default_sqlalchemy_integration(
    overrides: SqlalchemyIntegrationOptions | None = None,
) -> Integration | None:
    """创建 SqlalchemyIntegration

    Args:
        overrides: 覆盖参数,使用 SqlalchemyIntegrationOptions 类型获得类型提示

    Returns:
        SqlalchemyIntegration 实例,如果未安装 sqlalchemy 则返回 None

    Tip:
        - SQLAlchemy 集成会自动启用,如果检测到 sqlalchemy 包
        - 主要用于在 Sentry 中追踪数据库查询的性能

    Example:
        >>> from lush_sentryx.integrations.extras import default_sqlalchemy_integration
        >>> import sentry_sdk
        >>>
        >>> integration = default_sqlalchemy_integration()
        >>> if integration:
        ...     sentry_sdk.init(
        ...         dsn="...",
        ...         integrations=[integration],
        ...     )
    """
    try:
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        params: dict[str, Any] = {}
        if overrides:
            params.update(overrides)

        return SqlalchemyIntegration(**params)
    except ImportError:
        _logger.debug("SQLAlchemy integration not available (sqlalchemy not installed)")
        return None


def default_redis_integration(
    overrides: RedisIntegrationOptions | None = None,
) -> Integration | None:
    """创建 RedisIntegration

    Args:
        overrides: 覆盖参数,使用 RedisIntegrationOptions 类型获得类型提示

    Returns:
        RedisIntegration 实例,如果未安装 redis 则返回 None

    Tip:
        - Redis 集成会自动启用,如果检测到 redis 包
        - 用于追踪 Redis 命令的性能

    Example:
        >>> from lush_sentryx.integrations.extras import default_redis_integration
        >>> import sentry_sdk
        >>>
        >>> # 自定义数据截断大小
        >>> integration = default_redis_integration({"max_data_size": 2048})
        >>> if integration:
        ...     sentry_sdk.init(
        ...         dsn="...",
        ...         integrations=[integration],
        ...     )
    """
    try:
        from sentry_sdk.integrations.redis import RedisIntegration

        params: dict[str, Any] = {}
        if overrides:
            params.update(overrides)

        return RedisIntegration(**params)
    except ImportError:
        _logger.debug("Redis integration not available (redis not installed)")
        return None


def default_logging_integration(
    overrides: LoggingIntegrationOptions | None = None,
) -> Integration | None:
    """创建 LoggingIntegration

    Args:
        overrides: 覆盖参数,使用 LoggingIntegrationOptions 类型获得类型提示

    Returns:
        LoggingIntegration 实例

    Tip:
        - Logging 集成默认启用
        - 默认将 INFO 及以上级别日志记录为面包屑
        - 默认将 ERROR 及以上级别日志作为事件发送

    Example:
        >>> from lush_sentryx.integrations.extras import default_logging_integration
        >>> import sentry_sdk
        >>> import logging
        >>>
        >>> # 使用 SDK 默认配置
        >>> sentry_sdk.init(
        ...     dsn="...",
        ...     integrations=[default_logging_integration()],
        ... )
        >>>
        >>> # 只有 CRITICAL 级别作为事件发送
        >>> sentry_sdk.init(
        ...     dsn="...",
        ...     integrations=[
        ...         default_logging_integration(
        ...             {
        ...                 "level": logging.INFO,
        ...                 "event_level": logging.CRITICAL,
        ...             }
        ...         )
        ...     ],
        ... )
    """
    try:
        from sentry_sdk.integrations.logging import LoggingIntegration

        params: dict[str, Any] = {}
        if overrides:
            params.update(overrides)

        return LoggingIntegration(**params)
    except ImportError:
        _logger.debug("Logging integration not available")
        return None


def default_common_integrations(
    *,
    enable_sqlalchemy: bool = True,
    enable_redis: bool = True,
    enable_logging: bool = True,
    logging_level: int = logging.INFO,
    logging_event_level: int | None = None,
    sqlalchemy_options: SqlalchemyIntegrationOptions | None = None,
    redis_options: RedisIntegrationOptions | None = None,
) -> list[Integration]:
    """创建一组通用集成

    这是一个便捷函数,用于创建常用的通用集成组合(SQLAlchemy、Redis、Logging).

    设计原则:
        - 默认启用所有通用集成
        - 各集成参数让 SDK 使用默认值
        - 用户可通过 TypedDict options 进行精细控制

    Args:
        enable_sqlalchemy: 是否启用 SQLAlchemy 集成
        enable_redis: 是否启用 Redis 集成
        enable_logging: 是否启用 Logging 集成
        logging_level: 记录为面包屑的最低日志级别 (SDK 默认: INFO)
        logging_event_level: 作为事件发送的最低日志级别 (SDK 默认: ERROR, None 禁用)
        sqlalchemy_options: SQLAlchemy 集成的额外参数
        redis_options: Redis 集成的额外参数

    Returns:
        可用集成的列表(未安装的依赖会被跳过)

    Example:
        >>> from lush_sentryx.integrations.extras import default_common_integrations
        >>> from lush_sentryx.integrations.fastapi import default_fastapi_integrations
        >>> import sentry_sdk
        >>> import logging
        >>>
        >>> sentry_sdk.init(
        ...     dsn="...",
        ...     integrations=[
        ...         *default_fastapi_integrations(),
        ...         *default_common_integrations(
        ...             enable_sqlalchemy=True,
        ...             enable_redis=True,
        ...             logging_level=logging.INFO,
        ...             logging_event_level=logging.CRITICAL,
        ...         ),
        ...     ],
        ... )
        >>>
        >>> # 使用 TypedDict 配置 Redis
        >>> sentry_sdk.init(
        ...     dsn="...",
        ...     integrations=[
        ...         *default_common_integrations(
        ...             redis_options={"max_data_size": 2048},
        ...         ),
        ...     ],
        ... )
    """
    integrations: list[Integration] = []

    if enable_sqlalchemy:
        integration = default_sqlalchemy_integration(sqlalchemy_options)
        if integration:
            integrations.append(integration)

    if enable_redis:
        integration = default_redis_integration(redis_options)
        if integration:
            integrations.append(integration)

    if enable_logging:
        logging_opts: LoggingIntegrationOptions = {}
        if logging_level != logging.INFO:  # 只在非默认值时设置
            logging_opts["level"] = logging_level
        if logging_event_level is not None:  # None 表示用户没有指定,使用 SDK 默认
            logging_opts["event_level"] = logging_event_level

        integration = default_logging_integration(logging_opts or None)
        if integration:
            integrations.append(integration)

    return integrations
