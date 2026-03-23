"""速率限制实现: 节流(Throttle)和防抖(Debounce)

提供基于 FastAPI 的速率限制守卫依赖, 支持参数化实例以便在不同路由中复用.

- ThrottleGuard: 节流 - 在固定时间窗口内只允许第一次请求通过
- DebounceGuard: 防抖 - 每次请求重置计时器,只有在窗口期内无新请求时才允许执行
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from inspect import Parameter, Signature
from typing import Any, Generic, Literal, TypeVar

from fastapi import Depends, HTTPException, Request, status
from typing_extensions import override

from lush_redisx.async_redis import AsyncRedisManager

TContext = TypeVar("TContext")
RedisDependency = Callable[..., Awaitable[AsyncRedisManager] | AsyncRedisManager]
KeyBuilderCallable = Callable[[Request, Any | None], Awaitable[str] | str]
ExceptionFactoryCallable = Callable[[Request, str, float, Any | None], Exception]


async def _maybe_await_str(value: Awaitable[str] | str) -> str:
    if isinstance(value, str):
        return value
    return await value


class RateLimitKeyBuilder(ABC, Generic[TContext]):
    """速率限制键构建器基类.

    用于自定义速率限制的 Redis 键生成逻辑.

    Type Parameters:
        TContext: 上下文类型,可以是任意业务标识
    """

    @abstractmethod
    async def build_key(self, request: Request, context: TContext | None = None) -> str:
        """构建速率限制 Redis key.

        Args:
            request: FastAPI 请求对象
            context: 上下文信息

        Returns:
            str: Redis 键名
        """


class ClientIPRateLimitKeyBuilder(RateLimitKeyBuilder[TContext]):
    """基于客户端 IP 的默认速率限制键构建器.

    默认的键构建器实现,基于客户端 IP 生成限流键.
    支持从 X-Forwarded-For 头获取真实 IP.

    Attributes:
        action: 操作名称
        limit_type: 限制类型,可以是 "throttle" 或 "debounce"
    """

    def __init__(self, action: str, limit_type: Literal["throttle", "debounce"] = "throttle") -> None:
        """初始化键构建器.

        Args:
            action: 操作名称,如 "submit_form"
            limit_type: 限制类型,默认为 "throttle"
        """
        self.action = action
        self.limit_type = limit_type

    @override
    async def build_key(self, request: Request, context: TContext | None = None) -> str:
        """构建基于客户端 IP 的 Redis 键.

        Args:
            request: FastAPI 请求对象
            context: 上下文信息(未使用)

        Returns:
            str: Redis 键名,格式为 "{limit_type}:{action}:{client_ip}"
        """
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"

        return f"{self.limit_type}:{self.action}:{client_ip}"


class ThrottleGuard(Generic[TContext]):
    """节流守卫: 在固定时间窗口内只允许第一次请求通过.

    Type Parameters:
        TContext: 上下文类型

    Attributes:
        _window_seconds: 时间窗口(秒)
        _redis_dependency: Redis 管理器依赖函数
        _key_builder: 键构建器
        _context_dependency: 上下文依赖函数
        _context_annotation: 上下文类型注解
        _exception_factory: 异常工厂函数

    适用场景:
        - API 限流
        - 防止短时间内重复提交
        - 限制资源访问频率

    Examples:
        创建一个 60 秒的节流守卫::

            submit_throttle = ThrottleGuard(window_seconds=60, redis_dependency=get_redis_manager, action="submit_form")


            @app.post("/submit")
            async def submit(throttle: None = Depends(submit_throttle)):
                return {"status": "ok"}

        使用自定义异常::

            def custom_exception_factory(*args, **kwargs):
                return MyRateLimitException("请求过于频繁")


            submit_throttle = ThrottleGuard(
                window_seconds=60,
                redis_dependency=get_redis_manager,
                action="submit_form",
                exception_factory=custom_exception_factory,
            )
    """

    def __init__(
        self,
        window_seconds: int,
        *,
        redis_dependency: RedisDependency,
        key_builder: RateLimitKeyBuilder[TContext] | KeyBuilderCallable | None = None,
        action: str = "default",
        context_dependency: Callable[..., Awaitable[TContext] | TContext] | None = None,
        context_annotation: Any = Any,
        exception_factory: ExceptionFactoryCallable | None = None,
    ) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds 必须大于 0")

        self._window_seconds = window_seconds
        self._redis_dependency = redis_dependency
        self._key_builder: RateLimitKeyBuilder[TContext] | KeyBuilderCallable = key_builder or ClientIPRateLimitKeyBuilder(
            action, "throttle"
        )
        self._context_dependency = context_dependency
        self._context_annotation = context_annotation
        self._exception_factory = exception_factory

        parameters = [
            Parameter("request", Parameter.POSITIONAL_OR_KEYWORD, annotation=Request),
            Parameter(
                "redis_mgr",
                Parameter.POSITIONAL_OR_KEYWORD,
                default=Depends(self._redis_dependency),
                annotation=AsyncRedisManager,
            ),
        ]
        if self._context_dependency is not None:
            parameters.append(
                Parameter(
                    "context",
                    Parameter.POSITIONAL_OR_KEYWORD,
                    default=Depends(self._context_dependency),
                    annotation=self._context_annotation,
                )
            )

        self.__signature__ = Signature(parameters=parameters)

    async def __call__(
        self,
        request: Request,
        redis_mgr: AsyncRedisManager,
        context: TContext | None = None,
    ) -> None:
        """执行节流检查.

        Args:
            request: FastAPI 请求对象
            redis_mgr: Redis 管理器实例
            context: 上下文信息

        Raises:
            HTTPException: 如果超过速率限制且未提供 exception_factory
            Exception: 如果超过速率限制且提供了 exception_factory
        """
        redis_key = await self._build_key(request, context)
        result = await redis_mgr.op_prefixed.throttle_check_and_set(
            redis_key,
            window_seconds=self._window_seconds,
        )

        if getattr(result, "allowed", False):
            return

        remaining_seconds = float(getattr(result, "remaining_seconds", 0.0))
        redis_result_key = getattr(result, "redis_key", redis_key)

        # 如果提供了自定义异常工厂,使用它
        if self._exception_factory is not None:
            raise self._exception_factory(request, redis_result_key, remaining_seconds, context)

        # 否则抛出标准 HTTPException
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
        )

    async def _build_key(self, request: Request, context: TContext | None) -> str:
        """构建 Redis 键.

        Args:
            request: FastAPI 请求对象
            context: 上下文信息

        Returns:
            str: Redis 键名
        """
        builder = self._key_builder
        if isinstance(builder, RateLimitKeyBuilder):
            return await builder.build_key(request, context)

        return await _maybe_await_str(builder(request, context))


class DebounceGuard(Generic[TContext]):
    """防抖守卫: 每次请求重置计时器,只有在窗口期内无新请求时才允许执行.

    Type Parameters:
        TContext: 上下文类型

    Attributes:
        _window_seconds: 时间窗口(秒)
        _redis_dependency: Redis 管理器依赖函数
        _key_builder: 键构建器
        _context_dependency: 上下文依赖函数
        _context_annotation: 上下文类型注解
        _exception_factory: 异常工厂函数

    适用场景:
        - 搜索输入防抖
        - 自动保存功能
        - 实时验证(等用户停止输入后再验证)

    Note:
        防抖会拒绝窗口期内的所有请求,只有在最后一次请求后等待足够时间才允许

    Examples:
        创建一个 3 秒的防抖守卫::

            search_debounce = DebounceGuard(window_seconds=3, redis_dependency=get_redis_manager, action="search")


            @app.get("/search")
            async def search(q: str, debounce: None = Depends(search_debounce)):
                return {"results": []}
    """

    def __init__(
        self,
        window_seconds: int,
        *,
        redis_dependency: RedisDependency,
        key_builder: RateLimitKeyBuilder[TContext] | KeyBuilderCallable | None = None,
        action: str = "default",
        context_dependency: Callable[..., Awaitable[TContext] | TContext] | None = None,
        context_annotation: Any = Any,
        exception_factory: ExceptionFactoryCallable | None = None,
    ) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds 必须大于 0")

        self._window_seconds = window_seconds
        self._redis_dependency = redis_dependency
        self._key_builder: RateLimitKeyBuilder[TContext] | KeyBuilderCallable = key_builder or ClientIPRateLimitKeyBuilder(
            action, "debounce"
        )
        self._context_dependency = context_dependency
        self._context_annotation = context_annotation
        self._exception_factory = exception_factory

        parameters = [
            Parameter("request", Parameter.POSITIONAL_OR_KEYWORD, annotation=Request),
            Parameter(
                "redis_mgr",
                Parameter.POSITIONAL_OR_KEYWORD,
                default=Depends(self._redis_dependency),
                annotation=AsyncRedisManager,
            ),
        ]
        if self._context_dependency is not None:
            parameters.append(
                Parameter(
                    "context",
                    Parameter.POSITIONAL_OR_KEYWORD,
                    default=Depends(self._context_dependency),
                    annotation=self._context_annotation,
                )
            )

        self.__signature__ = Signature(parameters=parameters)

    async def __call__(
        self,
        request: Request,
        redis_mgr: AsyncRedisManager,
        context: TContext | None = None,
    ) -> None:
        redis_key = await self._build_key(request, context)
        result = await redis_mgr.op_prefixed.debounce_check_and_set(
            redis_key,
            window_seconds=self._window_seconds,
        )

        if getattr(result, "allowed", False):
            return

        remaining_seconds = float(getattr(result, "remaining_seconds", 0.0))
        redis_result_key = getattr(result, "redis_key", redis_key)

        # 如果提供了自定义异常工厂,使用它
        if self._exception_factory is not None:
            raise self._exception_factory(request, redis_result_key, remaining_seconds, context)

        # 否则抛出标准 HTTPException
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
        )

    async def _build_key(self, request: Request, context: TContext | None) -> str:
        builder = self._key_builder
        if isinstance(builder, RateLimitKeyBuilder):
            return await builder.build_key(request, context)

        return await _maybe_await_str(builder(request, context))


def throttle_guard_factory(
    window_seconds: int,
    *,
    redis_dependency: RedisDependency,
    key_builder: RateLimitKeyBuilder[TContext] | KeyBuilderCallable | None = None,
    action: str = "default",
    context_dependency: Callable[..., Awaitable[TContext] | TContext] | None = None,
    context_annotation: Any = Any,
    exception_factory: ExceptionFactoryCallable | None = None,
) -> ThrottleGuard[TContext]:
    """创建节流守卫的工厂函数.

    Args:
        window_seconds: 时间窗口(秒)
        redis_dependency: Redis 管理器依赖函数
        key_builder: 自定义键构建器
        action: 操作名称
        context_dependency: 上下文依赖函数
        context_annotation: 上下文类型注解
        exception_factory: 自定义异常工厂函数

    Returns:
        ThrottleGuard[TContext]: 节流守卫实例
    """
    return ThrottleGuard(
        window_seconds,
        redis_dependency=redis_dependency,
        key_builder=key_builder,
        action=action,
        context_dependency=context_dependency,
        context_annotation=context_annotation,
        exception_factory=exception_factory,
    )


def debounce_guard_factory(
    window_seconds: int,
    *,
    redis_dependency: RedisDependency,
    key_builder: RateLimitKeyBuilder[TContext] | KeyBuilderCallable | None = None,
    action: str = "default",
    context_dependency: Callable[..., Awaitable[TContext] | TContext] | None = None,
    context_annotation: Any = Any,
    exception_factory: ExceptionFactoryCallable | None = None,
) -> DebounceGuard[TContext]:
    """创建防抖守卫的工厂函数.

    Args:
        window_seconds: 时间窗口(秒)
        redis_dependency: Redis 管理器依赖函数
        key_builder: 自定义键构建器
        action: 操作名称
        context_dependency: 上下文依赖函数
        context_annotation: 上下文类型注解
        exception_factory: 自定义异常工厂函数

    Returns:
        DebounceGuard[TContext]: 防抖守卫实例
    """
    return DebounceGuard(
        window_seconds,
        redis_dependency=redis_dependency,
        key_builder=key_builder,
        action=action,
        context_dependency=context_dependency,
        context_annotation=context_annotation,
        exception_factory=exception_factory,
    )


__all__ = [
    "ClientIPRateLimitKeyBuilder",
    "DebounceGuard",
    "ExceptionFactoryCallable",
    "KeyBuilderCallable",
    "RateLimitKeyBuilder",
    "ThrottleGuard",
    "debounce_guard_factory",
    "throttle_guard_factory",
]
