"""Sentryx 核心模块

定义 Sentry 集成所需的统一配置类和管理器.
将 SentryConfig 和 SentryManager 放在同一文件中避免循环导入.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from typing import Any, Literal

import sentry_sdk
from lush_sentryx_core import (
    SENTRY_DEFAULT_DENYLIST,
    create_additional_filter,
    create_transaction_filter,
    custom_repr,
)
from lush_sentryx_core.sdk.v2 import mask_user_email_partially
from lush_sentryx_core.sdk.v2.types import EventProcessor
from sentry_sdk.integrations import Integration
from sentry_sdk.scrubber import EventScrubber

from lush_sentryx.scrubbers import create_enhanced_scrubber, get_all_sensitive_fields

_logger = logging.getLogger(__name__)

DEFAULT_EXTENDED_DENYLIST: frozenset[str] = frozenset(
    {
        "phone",
        "mobile",
        "id_card",
        "bank_account",
        "card_number",
        "account_number",
    }
)


def chain_before_send(
    base_hook: EventProcessor,
    extra_hook: EventProcessor | None = None,
) -> EventProcessor:
    """链式组合两个 before_send 钩子"""
    if extra_hook is None:
        return base_hook

    from lush_sentryx_core.sdk.v2.types import Event, Hint

    def chained(event: Event, hint: Hint) -> Event | None:
        result = base_hook(event, hint)
        if result is None:
            return None
        return extra_hook(result, hint)

    return chained


# region 默认 Integration 工厂函数


def default_sqlalchemy_integration() -> Integration:
    """默认 SQLAlchemy 集成工厂"""
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    return SqlalchemyIntegration()


def default_redis_integration() -> Integration:
    """默认 Redis 集成工厂"""
    # sentry-sdk 的 RedisIntegration 在 setup 阶段需要 redis client 存在；
    # 作为独立包时应在缺少依赖时自动降级,而不是让 init 失败。
    import importlib

    _ = importlib.import_module("redis")

    from sentry_sdk.integrations.redis import RedisIntegration

    return RedisIntegration()


def default_logging_integration(
    level: int = logging.INFO,
    event_level: int = logging.ERROR,
) -> Callable[[], Integration]:
    """默认 Logging 集成工厂生成器"""

    def factory() -> Integration:
        from sentry_sdk.integrations.logging import LoggingIntegration

        return LoggingIntegration(level=level, event_level=event_level)

    return factory


# endregion


class SentryConfig:
    """统一的 Sentry 配置类(纯 Python 实现)

    提供类型安全的配置参数,支持验证和默认值.
    可直接初始化 Sentry SDK 或创建 SentryManager 实例.

    Example:
        基本配置(直接初始化):
            >>> config = SentryConfig(dsn="https://xxx@sentry.io/123", enabled=True, environment="production")
            >>> config.init()

        使用 SentryManager:
            >>> config = SentryConfig(dsn="https://xxx@sentry.io/123", enabled=True)
            >>> manager = config.create_manager()
            >>> if manager.init():
            ...     manager.capture_message("Service started")

        完整配置:
            >>> config = SentryConfig(
            ...     dsn="https://xxx@sentry.io/123",
            ...     enabled=True,
            ...     environment="production",
            ...     service_name="my-service",
            ...     service_version="2.1.0",
            ...     additional_denylist={"custom_secret", "internal_token"},
            ...     traces_sample_rate=0.1,
            ... )

    Note:
        - 生产环境建议: send_default_pii=False
        - traces_sample_rate 设置为 0.0 可以禁用性能追踪,节省配额
        - additional_denylist 使用子串匹配,不区分大小写
        - 业务特定敏感字段通过 additional_denylist 参数传入

    Raises:
        ValueError: 当 traces_sample_rate 不在 0.0-1.0 范围内时抛出
    """

    __slots__ = (
        "additional_denylist",
        "attach_stacktrace",
        "debug",
        "dsn",
        "enabled",
        "environment",
        "extra_before_send",
        "extra_sentry_sdk_init_kwargs",
        "include_local_variables",
        "integrations",
        "logger",
        "logging_event_level",
        "logging_integration",
        "logging_level",
        "max_breadcrumbs",
        "redis_integration",
        "send_default_pii",
        "service_name",
        "service_version",
        "traces_sample_rate",
    )

    dsn: str
    enabled: bool
    environment: str
    service_name: str
    service_version: str
    traces_sample_rate: float
    max_breadcrumbs: int
    send_default_pii: bool
    attach_stacktrace: bool
    include_local_variables: bool
    debug: bool
    additional_denylist: set[str]
    integrations: list[Integration]
    extra_before_send: EventProcessor | None
    extra_sentry_sdk_init_kwargs: dict[str, Any]
    redis_integration: Callable[[], Integration] | None
    logging_integration: Callable[[], Integration] | None
    logging_level: int
    logging_event_level: int
    logger: logging.Logger | None

    def __init__(
        self,
        dsn: str = "",
        enabled: bool = True,
        environment: str = "production",
        service_name: str = "service",
        service_version: str = "1.0.0",
        # SDK 行为控制
        traces_sample_rate: float = 0.0,
        max_breadcrumbs: int = 50,
        send_default_pii: bool = False,
        attach_stacktrace: bool = True,
        include_local_variables: bool = True,
        debug: bool = False,
        # 敏感数据过滤
        additional_denylist: set[str] | None = None,
        # 集成与钩子
        integrations: list[Integration] | None = None,
        extra_before_send: EventProcessor | None = None,
        extra_sentry_sdk_init_kwargs: dict[str, Any] | None = None,
        # Integration 工厂函数
        redis_integration: Callable[[], Integration] | None = default_redis_integration,
        logging_integration: Callable[[], Integration] | None = None,
        logging_level: int = logging.INFO,
        logging_event_level: int = logging.ERROR,
        # 日志
        logger: logging.Logger | None = None,
    ) -> None:
        if not (0.0 <= traces_sample_rate <= 1.0):
            raise ValueError(f"traces_sample_rate must be between 0.0 and 1.0, got {traces_sample_rate}")

        self.dsn = dsn
        self.enabled = enabled
        self.environment = environment
        self.service_name = service_name
        self.service_version = service_version
        self.traces_sample_rate = traces_sample_rate
        self.max_breadcrumbs = max_breadcrumbs
        self.send_default_pii = send_default_pii
        self.attach_stacktrace = attach_stacktrace
        self.include_local_variables = include_local_variables
        self.debug = debug
        self.additional_denylist = additional_denylist if additional_denylist is not None else set()
        self.integrations = integrations if integrations is not None else []
        self.extra_before_send = extra_before_send
        self.extra_sentry_sdk_init_kwargs = extra_sentry_sdk_init_kwargs if extra_sentry_sdk_init_kwargs is not None else {}
        self.redis_integration = redis_integration
        self.logging_integration = logging_integration
        self.logging_level = logging_level
        self.logging_event_level = logging_event_level
        self.logger = logger

    def collect_integrations(self) -> list[Integration]:
        """收集通用 Integration 列表

        子类应重写此方法,先调用 super() 获取基础列表,再添加框架特定的集成.
        """
        integrations: list[Integration] = []

        if self.redis_integration is not None:
            try:
                integrations.append(self.redis_integration())
            except (ImportError, Exception):
                _logger.debug("Redis integration not available")

        if self.logging_integration is not None:
            try:
                integrations.append(self.logging_integration())
            except (ImportError, Exception):
                _logger.debug("Logging integration not available")
        else:
            with contextlib.suppress(ImportError, Exception):
                integrations.append(default_logging_integration(self.logging_level, self.logging_event_level)())

        # 添加用户直接传入的集成
        if self.integrations:
            integrations.extend(self.integrations)

        return integrations

    def init(self) -> bool:
        """初始化 Sentry SDK

        直接初始化 Sentry SDK,不创建 SentryManager.
        如果需要 SentryManager 的完整功能,请使用 create_manager() 方法.

        Returns:
            初始化是否成功
        """
        if not self.enabled or not self.dsn:
            _logger.info("Sentry 未启用或 DSN 未配置")
            return False

        all_denylist: set[str] = set(SENTRY_DEFAULT_DENYLIST) | set(DEFAULT_EXTENDED_DENYLIST) | set(self.additional_denylist)

        base_before_send = create_additional_filter(all_denylist)
        final_before_send = chain_before_send(base_before_send, self.extra_before_send)

        integrations = self.collect_integrations()

        _ = sentry_sdk.init(
            dsn=self.dsn,
            environment=self.environment,
            send_default_pii=self.send_default_pii,
            attach_stacktrace=self.attach_stacktrace,
            include_local_variables=self.include_local_variables,
            custom_repr=custom_repr,
            traces_sample_rate=self.traces_sample_rate,
            event_scrubber=EventScrubber(denylist=list(all_denylist)),
            before_send=final_before_send,
            before_send_transaction=create_transaction_filter(),
            max_breadcrumbs=self.max_breadcrumbs,
            integrations=integrations,
            debug=self.debug,
            **self.extra_sentry_sdk_init_kwargs,
        )

        sentry_sdk.set_tag("service", self.service_name)
        _logger.info("Sentry 初始化成功, 环境: %s, 服务: %s", self.environment, self.service_name)
        return True

    def create_manager(self) -> SentryManager:
        """创建 SentryManager 实例

        SentryManager 提供更丰富的功能,包括:
        - capture_exception: 捕获异常
        - capture_message: 发送消息
        - set_user_context: 设置用户上下文
        - add_breadcrumb: 添加面包屑
        - check_connection: 检查连接状态

        Returns:
            SentryManager 实例(未初始化,需要调用 manager.init())

        Example:
            >>> config = SentryConfig(dsn="...", service_name="my-service")
            >>> manager = config.create_manager()
            >>> if manager.init():
            ...     manager.capture_message("Service started")
        """
        return SentryManager(self, logger=self.logger)


class SentryManager:
    """Sentry 错误追踪管理器

    提供完整的 Sentry 集成功能,包括错误追踪、性能监控、敏感数据过滤等.

    Args:
        config: Sentry 配置对象
        logger: 可选的日志记录器,默认使用内置 logger

    Attributes:
        config: Sentry 配置对象
        is_initialized: Sentry 是否已成功初始化

    Example:
        基本使用:
            >>> config = SentryConfig(dsn="...", enabled=True)
            >>> manager = SentryManager(config)
            >>> manager.init()
            >>> manager.capture_exception(exception)

        自定义logger:
            >>> import logging
            >>> custom_logger = logging.getLogger("my_app")
            >>> manager = SentryManager(config, logger=custom_logger)

        完整示例:
            >>> config = SentryConfig(
            ...     dsn="https://xxx@sentry.io/123",
            ...     enabled=True,
            ...     environment="production",
            ...     service_name="my-service",
            ...     additional_denylist={"custom_secret"},
            ... )
            >>> manager = SentryManager(config)
            >>> if manager.init():
            ...     manager.capture_message("Service started", level="info")
            ...     manager.set_tag("version", "2.0.0")

    Note:
        - 每个实例独立管理自己的配置
        - 支持多实例场景 (不同服务可以使用不同配置)
        - 初始化失败不会抛出异常,只是返回 False
    """

    def __init__(
        self,
        config: SentryConfig,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        """Sentry 是否已成功初始化"""
        return self._initialized

    def init(self) -> bool:
        """初始化 Sentry SDK

        配置企业级 Sentry SDK,包含完整的错误追踪、性能监控、敏感数据过滤和多种集成.
        此函数实现了符合 GDPR 和企业安全标准的数据保护机制.

        Returns:
            bool: 初始化状态
                - True: Sentry 成功初始化,所有安全过滤器已激活
                - False: 初始化失败或被跳过(未启用/无DSN配置)

        Raises:
            不抛出异常,所有错误都会被捕获并记录日志
        """
        if not self.config.enabled:
            self.logger.info("Sentry 未启用, 跳过初始化")
            return False

        if not self.config.dsn:
            self.logger.warning("Sentry DSN 未配置, 跳过初始化")
            return False

        try:
            # 按照官方文档创建 EventScrubber (SDK 2.x)
            enhanced_scrubber = create_enhanced_scrubber(
                denylist=self.config.additional_denylist,
            )

            # 计算所有敏感字段 (用于深度清理)
            all_sensitive_fields = get_all_sensitive_fields(
                additional_denylist=self.config.additional_denylist,
            )

            # 收集框架特定集成 (调用 collect_integrations 而非直接使用 integrations)
            integrations = self.config.collect_integrations()

            # 链式钩子: base_before_send + extra_before_send
            base_before_send = create_additional_filter(all_sensitive_fields)
            final_before_send = chain_before_send(base_before_send, self.config.extra_before_send)

            _ = sentry_sdk.init(
                dsn=self.config.dsn,
                environment=self.config.environment,
                # 错误追踪设置
                send_default_pii=self.config.send_default_pii,
                attach_stacktrace=self.config.attach_stacktrace,
                include_local_variables=self.config.include_local_variables,
                # 自定义变量序列化,保持基本类型清晰(避免 repr() 多余引号)
                custom_repr=custom_repr,
                traces_sample_rate=self.config.traces_sample_rate,
                # 使用 EventScrubber 自动清理敏感数据
                event_scrubber=enhanced_scrubber,
                integrations=integrations,
                before_send=final_before_send,  # 链式钩子
                before_send_transaction=create_transaction_filter(),  # 事务名称过滤
                max_breadcrumbs=self.config.max_breadcrumbs,
                debug=self.config.debug,
            )

            # 标记 Sentry 已初始化
            self._initialized = True

            # 设置默认标签
            try:
                if self.config.service_name:
                    sentry_sdk.set_tag("service", self.config.service_name)
                sentry_sdk.set_tag("version", self.config.service_version)
                sentry_sdk.set_tag("environment", self.config.environment)
            except Exception:
                self.logger.debug("设置默认 Sentry 标签失败, 跳过")

            self.logger.info("Sentry 初始化成功, 环境: %s", self.config.environment)

        except ImportError:
            self.logger.exception("Sentry SDK 导入失败")
            self._initialized = False
            return False
        except Exception:
            self.logger.exception("Sentry 初始化失败")
            self._initialized = False
            return False
        else:
            return True

    def capture_exception(
        self,
        exception: Exception,
        extras: dict[str, Any] | None = None,
        tags: dict[str, str] | None = None,
        user: dict[str, Any] | None = None,
        **scope_kwargs: Any,
    ) -> None:
        """安全地捕获异常到 Sentry,包含降级处理 - 并发安全版本"""
        try:
            with sentry_sdk.new_scope() as scope:
                if extras:
                    for k, v in extras.items():
                        scope.set_extra(k, v)
                if tags:
                    for k, v in tags.items():
                        scope.set_tag(k, v)
                if user:
                    scope.set_user(user)

                for key, value in scope_kwargs.items():
                    if hasattr(scope, f"set_{key}"):
                        getattr(scope, f"set_{key}")(value)
                    elif key == "level":
                        scope.level = value
                    elif key == "fingerprint":
                        scope.fingerprint = value

                _ = sentry_sdk.capture_exception(exception)
        except Exception:
            self.logger.exception("Sentry 异常捕获失败, 已降级到本地日志")
            self.logger.exception("原始异常: %s", exception)

    def capture_message(
        self,
        message: str,
        level: Literal["fatal", "critical", "error", "warning", "info", "debug"] = "info",
        extras: dict[str, Any] | None = None,
        tags: dict[str, str] | None = None,
        user: dict[str, Any] | None = None,
        **scope_kwargs: Any,
    ) -> None:
        """安全地发送消息到 Sentry,包含降级处理 - 并发安全版本"""
        try:
            with sentry_sdk.new_scope() as scope:
                if extras:
                    for k, v in extras.items():
                        scope.set_extra(k, v)
                if tags:
                    for k, v in tags.items():
                        scope.set_tag(k, v)
                if user:
                    scope.set_user(user)

                for key, value in scope_kwargs.items():
                    if hasattr(scope, f"set_{key}"):
                        getattr(scope, f"set_{key}")(value)
                    elif key == "fingerprint":
                        scope.fingerprint = value

                _ = sentry_sdk.capture_message(message, level=level)
        except Exception:
            self.logger.exception("Sentry 消息发送失败, 已降级到本地日志")
            _ = getattr(self.logger, level.lower(), self.logger.info)(message)

    def set_user_context(
        self,
        user_data: dict[str, Any],
    ) -> None:
        """安全地设置用户上下文,包含降级处理和敏感信息保护"""
        try:
            safe_user_data = dict(user_data)
            mask_user_email_partially(safe_user_data)

            if not safe_user_data.get("id") and not safe_user_data.get("username"):
                self.logger.warning("用户上下文缺少有效的标识符(id或username)")

            sentry_sdk.set_user(safe_user_data)
            self.logger.debug("Sentry 用户上下文设置成功, 字段数: %d", len(safe_user_data))

        except Exception as e:
            self.logger.warning("Sentry 用户上下文设置失败: %s", e)

    def set_tag(
        self,
        key: str,
        value: str,
    ) -> None:
        """安全地设置标签,包含降级处理"""
        try:
            sentry_sdk.set_tag(key, value)
        except Exception as e:
            self.logger.warning("Sentry 标签设置失败: %s", e)

    def add_breadcrumb(
        self,
        message: str,
        category: str = "default",
        level: Literal["fatal", "critical", "error", "warning", "info", "debug"] = "info",
        **data: Any,
    ) -> None:
        """安全地添加 breadcrumbs,包含降级处理"""
        try:
            sentry_sdk.add_breadcrumb(message=message, category=category, level=level, data=data)
        except Exception as e:
            self.logger.debug("Sentry breadcrumbs 添加失败: %s", e)

    def check_connection(self, timeout: float = 30.0) -> bool:
        """检查 Sentry 服务连接状态"""
        if not self._initialized:
            self.logger.debug("Sentry SDK 未初始化,无法执行健康检查")
            return False
        try:
            _ = sentry_sdk.capture_message(
                "🏥 Sentry health check - 连接测试",
                level="info",
                fingerprint=["sentry-health-check"],
            )
            sentry_sdk.flush(timeout=timeout)
        except TimeoutError:
            self.logger.warning("Sentry 连接测试超时")
            return False
        except Exception as e:
            self.logger.warning("Sentry 连接测试失败: %s", e)
            return False
        else:
            return True

    def get_health_status(self) -> dict[str, Any]:
        """获取 Sentry 服务健康状态的详细信息"""
        return {
            "is_initialized": self._initialized,
            "provider": "sentry-sdk-native",
        }
