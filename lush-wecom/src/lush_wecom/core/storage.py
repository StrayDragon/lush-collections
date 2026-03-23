import asyncio
import contextlib
import threading
import time
from abc import ABC, abstractmethod
from typing import cast

from typing_extensions import override

from lush_wecom.core.const import TOKEN_CACHE_BUFFER_SECONDS

with contextlib.suppress(ImportError):
    from redis import Redis
    from redis.asyncio import Redis as AsyncRedis

__all__ = [
    "AsyncBaseStorage",
    "AsyncMemoryStorage",
    "AsyncRedisStorage",
    "BaseStorage",
    "MemoryStorage",
    "RedisStorage",
]


class BaseStorage(ABC):
    """
    存储后端的抽象基类
    所有自定义存储实现都应继承此类并实现其方法
    """

    @abstractmethod
    def get(self, key: str) -> str | None:
        """根据 key 获取存储的 access_token 字符串"""

    @abstractmethod
    def set(self, key: str, value: str, expires_in: int) -> None:
        """将 access_token 字符串存入后端,并设置过期时间"""


class MemoryStorage(BaseStorage):
    """默认的内存存储实现"""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float]] = {}  # 存储键值对和过期时间
        self._lock: threading.Lock = threading.Lock()  # 线程安全锁

    @override
    def get(self, key: str) -> str | None:
        with self._lock:
            if key not in self._store:
                return None

            value, expires_at = self._store[key]
            if time.time() > expires_at:
                del self._store[key]  # 自动清理过期键
                return None
            return value

    @override
    def set(self, key: str, value: str, expires_in: int) -> None:
        with self._lock:
            # 留出缓冲时间,防止网络延迟等问题
            safe_expires_in = max(1, expires_in - TOKEN_CACHE_BUFFER_SECONDS)
            expires_at = time.time() + safe_expires_in
            self._store[key] = (value, expires_at)


class RedisStorage(BaseStorage):
    """使用 Redis 的存储实现"""

    def __init__(self, redis_client: "Redis") -> None:
        self.redis: "Redis" = redis_client  # noqa: UP037

    @override
    def get(self, key: str) -> str | None:
        return cast("str | None", self.redis.get(key))

    @override
    def set(self, key: str, value: str, expires_in: int) -> None:
        # 留出缓冲时间,防止网络延迟等问题
        safe_expires_in = max(1, expires_in - TOKEN_CACHE_BUFFER_SECONDS)
        _ = self.redis.set(key, value, ex=safe_expires_in)


class AsyncBaseStorage(ABC):
    """
    异步存储后端的抽象基类
    所有自定义异步存储实现都应继承此类并实现其方法
    """

    @abstractmethod
    async def get(self, key: str) -> str | None:
        """根据 key 获取存储的 access_token 字符串"""

    @abstractmethod
    async def set(self, key: str, value: str, expires_in: int) -> None:
        """将 access_token 字符串存入后端,并设置过期时间"""


class AsyncMemoryStorage(AsyncBaseStorage):
    """异步内存存储实现"""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float]] = {}  # 存储键值对和过期时间
        self._lock: asyncio.Lock = asyncio.Lock()  # 异步锁

    @override
    async def get(self, key: str) -> str | None:
        async with self._lock:
            if key not in self._store:
                return None

            value, expires_at = self._store[key]
            if time.time() > expires_at:
                del self._store[key]  # 自动清理过期键
                return None
            return value

    @override
    async def set(self, key: str, value: str, expires_in: int) -> None:
        async with self._lock:
            # 留出缓冲时间,防止网络延迟等问题
            safe_expires_in = max(1, expires_in - TOKEN_CACHE_BUFFER_SECONDS)
            expires_at = time.time() + safe_expires_in
            self._store[key] = (value, expires_at)


class AsyncRedisStorage(AsyncBaseStorage):
    """使用异步 Redis 的存储实现"""

    def __init__(self, redis_client: "AsyncRedis") -> None:
        self.redis: "AsyncRedis" = redis_client  # noqa: UP037

    @override
    async def get(self, key: str) -> str | None:
        result = await self.redis.get(key)
        return cast("str | None", result)

    @override
    async def set(self, key: str, value: str, expires_in: int) -> None:
        # 留出缓冲时间,防止网络延迟等问题
        safe_expires_in = max(1, expires_in - TOKEN_CACHE_BUFFER_SECONDS)
        await self.redis.set(key, value, ex=safe_expires_in)
