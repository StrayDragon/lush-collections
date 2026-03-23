"""Sentryx FastAPI 集成

提供 FastAPI 框架的特定集成功能和初始化工厂函数.

官方文档: https://docs.sentry.io/platforms/python/integrations/fastapi/

注意: FastAPI 基于 Starlette,需要同时配置 StarletteIntegration 和 FastApiIntegration
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from sentry_sdk.integrations import Integration
from typing_extensions import TypedDict, override

from lush_sentryx.core import SentryConfig, SentryManager, default_sqlalchemy_integration

if TYPE_CHECKING:
    from fastapi import Request

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TypedDict for type-safe overrides
# ---------------------------------------------------------------------------


class FastAPIIntegrationOptions(TypedDict, total=False):
    """FastApiIntegration 和 StarletteIntegration 参数类型定义

    所有字段均为可选.未指定的字段将使用 SDK 默认值.

    注意: StarletteIntegration 和 FastApiIntegration 共享这些参数,
          应同时配置相同的值以保持一致性.

    Attributes:
        transaction_style: 事务命名风格
            - "url": 使用 URL 路径 (如 "/catalog/product/{product_id}")
            - "endpoint": 使用端点名称 (如 "product_detail")
            SDK 默认值: "url"

        failed_request_status_codes: 视为失败应上报 Sentry 的 HTTP 状态码集合
            - 仅影响 HTTPException,未处理的异常始终上报
            - 示例: {500}, {400, *range(500, 600)}, set() (不上报)
            SDK 默认值: {*range(500, 600)} (所有 5xx)

        http_methods_to_capture: 需要创建事务的 HTTP 方法元组
            注意: OPTIONS 和 HEAD 默认不包含
            SDK 默认值: ("CONNECT", "DELETE", "GET", "PATCH", "POST", "PUT", "TRACE")
    """

    transaction_style: str
    failed_request_status_codes: set[int]
    http_methods_to_capture: tuple[str, ...]


class FastAPISentryConfig(SentryConfig):
    """FastAPI Sentry 配置

    Example:
        基础使用:
            >>> config = FastAPISentryConfig(dsn="...", service_name="my-service")
            >>> config.init()  # 简单初始化

        使用 SentryManager:
            >>> config = FastAPISentryConfig(dsn="...", service_name="my-service")
            >>> manager = config.create_manager()
            >>> if manager.init():
            ...     manager.capture_message("FastAPI service started")

        自定义失败状态码:
            >>> config = FastAPISentryConfig(
            ...     dsn="...",
            ...     failed_request_status_codes={500, 502, 503},
            ... )

        禁用 SQLAlchemy 集成:
            >>> config = FastAPISentryConfig(dsn="...", enable_sqlalchemy=False)
    """

    __slots__ = (
        "enable_sqlalchemy",
        "failed_request_status_codes",
        "sqlalchemy_integration_factory",
        "transaction_style",
    )

    transaction_style: str
    """事务命名风格 ("url" 或 "endpoint")"""

    failed_request_status_codes: set[int] | None
    """视为失败的 HTTP 状态码集合"""

    enable_sqlalchemy: bool
    """是否启用 SQLAlchemy 集成"""

    sqlalchemy_integration_factory: Callable[[], Integration] | None
    """SQLAlchemy 集成工厂函数"""

    def __init__(
        self,
        *,
        # FastAPI 特有参数
        transaction_style: str = "url",
        failed_request_status_codes: set[int] | None = None,
        enable_sqlalchemy: bool = True,
        sqlalchemy_integration_factory: Callable[[], Integration] | None = None,
        # 覆盖默认服务名
        service_name: str = "fastapi-service",
        # 其他基类参数
        **kwargs: Any,
    ) -> None:
        super().__init__(service_name=service_name, **kwargs)
        self.transaction_style = transaction_style
        self.failed_request_status_codes = failed_request_status_codes
        self.enable_sqlalchemy = enable_sqlalchemy
        self.sqlalchemy_integration_factory = sqlalchemy_integration_factory or default_sqlalchemy_integration

    @override
    def collect_integrations(self) -> list[Integration]:
        """收集 FastAPI 相关的 Integration 列表"""
        try:
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.starlette import StarletteIntegration
        except (ImportError, Exception) as e:
            raise ImportError("FastAPI integration requires 'fastapi'. Install: pip install lush-sentryx[fastapi]") from e

        starlette_kwargs: dict[str, Any] = {"transaction_style": self.transaction_style}
        fastapi_kwargs: dict[str, Any] = {"transaction_style": self.transaction_style}

        if self.failed_request_status_codes is not None:
            starlette_kwargs["failed_request_status_codes"] = self.failed_request_status_codes
            fastapi_kwargs["failed_request_status_codes"] = self.failed_request_status_codes

        integrations: list[Integration] = [
            StarletteIntegration(**starlette_kwargs),
            FastApiIntegration(**fastapi_kwargs),
        ]

        if self.enable_sqlalchemy and self.sqlalchemy_integration_factory is not None:
            try:
                integrations.append(self.sqlalchemy_integration_factory())
            except (ImportError, Exception):
                _logger.debug("SQLAlchemy integration not available")

        integrations.extend(super().collect_integrations())
        return integrations


def init_sentry_for_fastapi(cfg: FastAPISentryConfig) -> bool:
    """FastAPI 项目 Sentry 初始化(简化版)

    需要安装: pip install lush-sentryx[fastapi]

    Args:
        cfg: FastAPISentryConfig 配置对象

    Returns:
        初始化是否成功

    Example:
        >>> from lush_sentryx.integrations.fastapi import init_sentry_for_fastapi, FastAPISentryConfig
        >>>
        >>> # 基础使用
        >>> config = FastAPISentryConfig(dsn="...", service_name="my-service")
        >>> init_sentry_for_fastapi(config)
        >>>
        >>> # 自定义失败状态码
        >>> config = FastAPISentryConfig(
        ...     dsn="...",
        ...     failed_request_status_codes={500, 502, 503},
        ... )
        >>> init_sentry_for_fastapi(config)
        >>>
        >>> # 禁用 SQLAlchemy 集成
        >>> config = FastAPISentryConfig(dsn="...", enable_sqlalchemy=False)
        >>> init_sentry_for_fastapi(config)
        >>>
        >>> # 传递额外的 sentry_sdk.init() 参数
        >>> config = FastAPISentryConfig(
        ...     dsn="...",
        ...     extra_sentry_sdk_init_kwargs={"debug": True, "release": "1.0.0"},
        ... )
        >>> init_sentry_for_fastapi(config)
    """
    return cfg.init()


def create_sentry_manager_for_fastapi(cfg: FastAPISentryConfig) -> SentryManager:
    """创建 FastAPI 项目的 SentryManager 实例

    SentryManager 提供更丰富的功能,包括:
    - capture_exception: 捕获异常并发送到 Sentry
    - capture_message: 发送消息到 Sentry
    - set_user_context: 设置用户上下文
    - add_breadcrumb: 添加面包屑
    - check_connection: 检查 Sentry 连接状态

    需要安装: pip install lush-sentryx[fastapi]

    Args:
        cfg: FastAPISentryConfig 配置对象

    Returns:
        SentryManager 实例(未初始化,需要调用 manager.init())

    Example:
        >>> from lush_sentryx.integrations.fastapi import create_sentry_manager_for_fastapi, FastAPISentryConfig
        >>>
        >>> # 创建并初始化 manager
        >>> config = FastAPISentryConfig(dsn="...", service_name="my-service")
        >>> manager = create_sentry_manager_for_fastapi(config)
        >>> if manager.init():
        ...     manager.capture_message("FastAPI service started")
        >>>
        >>> # 在异常处理器中使用
        >>> @app.exception_handler(Exception)
        >>> async def handler(request: Request, exc: Exception):
        ...     manager.capture_exception(exc)
        ...     return JSONResponse({"error": "Internal Server Error"}, status_code=500)
        >>>
        >>> # 使用自定义 logger
        >>> import logging
        >>> config = FastAPISentryConfig(dsn="...", logger=logging.getLogger("my_app"))
        >>> manager = create_sentry_manager_for_fastapi(config)
    """
    return cfg.create_manager()


# ---------------------------------------------------------------------------
# Default Integration Factory
# ---------------------------------------------------------------------------


def default_fastapi_integrations(overrides: FastAPIIntegrationOptions | None = None) -> list[Integration]:
    """创建 FastAPI 集成列表(包含 StarletteIntegration 和 FastApiIntegration)

    使用此工厂函数创建 Integration,而非手动构建.
    这样可以确保使用最佳实践配置,同时保持对 SDK 新参数的即时支持.

    重要: FastAPI 基于 Starlette,必须同时配置两个 Integration.
          本函数自动处理这一点.

    设计原则:
        - 不设置任何默认值,完全使用 SDK 默认值
        - 用户 overrides 优先级最高
        - StarletteIntegration 和 FastApiIntegration 使用相同参数

    Args:
        overrides: 覆盖参数,使用 FastAPIIntegrationOptions 类型获得类型提示

    Returns:
        包含 StarletteIntegration 和 FastApiIntegration 的列表

    Tip (来自官方文档):
        - 未设置 send_default_pii 时,PII 信息 (用户ID、cookies等) 不会被发送
        - failed_request_status_codes 仅影响 HTTPException,
          未处理的异常始终上报

    Example:
        >>> # 使用 SDK 默认配置
        >>> integrations = default_fastapi_integrations()
        >>>
        >>> # 自定义失败状态码
        >>> integrations = default_fastapi_integrations(
        ...     {
        ...         "failed_request_status_codes": {500, 502, 503},
        ...     }
        ... )
        >>>
        >>> # 使用端点名称作为事务名
        >>> integrations = default_fastapi_integrations(
        ...     {
        ...         "transaction_style": "endpoint",
        ...     }
        ... )

    See Also:
        https://docs.sentry.io/platforms/python/integrations/fastapi/#options
    """
    try:
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except (ImportError, Exception) as e:
        raise ImportError("FastAPI integration requires 'fastapi'. Install: pip install lush-sentryx[fastapi]") from e

    # 不设置任何默认值,完全使用 SDK 默认值
    params: dict[str, Any] = {}

    # 合并用户 overrides
    if overrides:
        params.update(overrides)

    # StarletteIntegration 和 FastApiIntegration 使用相同参数
    return [
        StarletteIntegration(**params),
        FastApiIntegration(**params),
    ]


def set_sentry_context_from_request(
    manager: SentryManager,
    request: "Request",
    exc: Exception,
    get_user_id: Callable[["Request"], Any] | None = None,
    get_client_ip: Callable[["Request"], str | None] | None = None,
) -> None:
    """从 FastAPI Request 提取信息并设置到 Sentry 上下文

    从请求对象中提取有用的上下文信息(如HTTP方法、路径、用户信息等),
    并设置到 Sentry 事件中,帮助调试和追踪问题.

    Args:
        manager: SentryManager 实例
        request: FastAPI 请求对象 (或任何具有 method, url.path 属性的请求对象)
        exc: 捕获到的异常
        get_user_id: 可选的用户ID提取函数,接受 Request 返回用户ID
        get_client_ip: 可选的客户端IP提取函数,接受 Request 返回IP地址

    Note:
        - 这是一个同步函数,可以在异常处理器中直接调用
        - 如果提取信息失败,不会影响主流程
        - 所有敏感信息会被 Sentry 的过滤器自动处理
        - 此函数兼容任何具有类似 FastAPI Request 接口的请求对象

    Example:
        基本使用(不提取用户信息):
            >>> from lush_sentryx.integrations.fastapi import set_sentry_context_from_request
            >>> try:
            ...     process_request()
            ... except Exception as e:
            ...     set_sentry_context_from_request(manager, request, e)
            ...     raise

        提供自定义提取函数:
            >>> def extract_user_id(req: Request) -> str | None:
            ...     return req.headers.get("X-User-ID")
            >>>
            >>> def extract_client_ip(req: Request) -> str | None:
            ...     return req.client.host if req.client else None
            >>>
            >>> set_sentry_context_from_request(manager, request, exc, get_user_id=extract_user_id, get_client_ip=extract_client_ip)
    """
    try:
        manager.set_tag("http_method", request.method)
        manager.set_tag("endpoint", request.url.path)
        manager.set_tag("exception_type", type(exc).__name__)

        user_info: dict[str, Any] = {}

        if get_user_id:
            user_id = get_user_id(request)
            if user_id:
                user_info["id"] = user_id

        if get_client_ip:
            client_ip = get_client_ip(request)
            if client_ip:
                user_info["client_ip"] = client_ip

        if user_info:
            manager.set_user_context(user_info)

    except Exception as context_error:
        manager.logger.warning("设置 Sentry 上下文失败: %s", context_error)
