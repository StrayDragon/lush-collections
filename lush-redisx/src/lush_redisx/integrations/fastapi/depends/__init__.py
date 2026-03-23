"""FastAPI 依赖工厂: 提供 Redis 管理器注入工具和速率限制守卫."""

from typing import Annotated, ClassVar

from fastapi import Depends, Request

from lush_redisx.async_redis import AsyncRedisManager

from .mutex import (
    MutexGuard,
    MutexKeyBuilder,
    MutexLockInfo,
    UserIDMutexKeyBuilder,
    mutex_guard_factory,
)
from .rate_limit import (
    ClientIPRateLimitKeyBuilder,
    DebounceGuard,
    RateLimitKeyBuilder,
    ThrottleGuard,
    debounce_guard_factory,
    throttle_guard_factory,
)


class AsyncRedisManagerDepends:
    state_name: ClassVar[str] = "redis_mgr"

    @classmethod
    async def get_async_redis_manager(cls, request: Request) -> AsyncRedisManager:
        """从请求上下文中获取异步 Redis 管理器.

        Args:
            request (Request): 当前 FastAPI 请求对象.

        Returns:
            AsyncRedisManager: 预先注入到请求状态的 Redis 管理器实例.
        """
        return getattr(request.state, cls.state_name)


AsyncRedisManagerDep = Annotated[AsyncRedisManager, Depends(AsyncRedisManagerDepends.get_async_redis_manager)]

__all__ = [
    "AsyncRedisManagerDep",
    "AsyncRedisManagerDepends",
    "ClientIPRateLimitKeyBuilder",
    "DebounceGuard",
    "MutexGuard",
    "MutexKeyBuilder",
    "MutexLockInfo",
    "RateLimitKeyBuilder",
    "ThrottleGuard",
    "UserIDMutexKeyBuilder",
    "debounce_guard_factory",
    "mutex_guard_factory",
    "throttle_guard_factory",
]
