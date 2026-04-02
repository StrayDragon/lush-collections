from __future__ import annotations

import builtins
import contextlib
import dataclasses
import json
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import timedelta
from enum import Enum
from typing import Any, ParamSpec, TypeVar

import redis.asyncio as redis
import structlog
from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import RedisError
from structlog.typing import FilteringBoundLogger
from typing_extensions import override

T = TypeVar("T")
P = ParamSpec("P")
R = TypeVar("R")

_DEFAULT_LOGGER: FilteringBoundLogger = structlog.get_logger(__name__)


class SerializationMode(str, Enum):
    """序列化模式"""

    NONE = "none"
    JSON = "json"
    STRING = "string"


@dataclasses.dataclass(frozen=True, slots=True)
class DebounceResult:
    allowed: bool
    remaining_seconds: float
    redis_key: str


class RedisCacheStrategy(ABC):
    @abstractmethod
    def should_cache(self, value: Any) -> bool: ...

    @abstractmethod
    def ttl_for(self, value: Any, default_ttl_seconds: int) -> int: ...


class RedisCacheAll(RedisCacheStrategy):
    @override
    def should_cache(self, value: Any) -> bool:
        return True

    @override
    def ttl_for(self, value: Any, default_ttl_seconds: int) -> int:
        return default_ttl_seconds


class RedisSkipNone(RedisCacheStrategy):
    @override
    def should_cache(self, value: Any) -> bool:
        return value is not None

    @override
    def ttl_for(self, value: Any, default_ttl_seconds: int) -> int:
        return default_ttl_seconds


class RedisTTLNone(RedisCacheStrategy):
    def __init__(self, none_ttl: int | timedelta = 60) -> None:
        if isinstance(none_ttl, timedelta):
            self.none_ttl_seconds = int(none_ttl.total_seconds())
        else:
            self.none_ttl_seconds = int(none_ttl)

    @override
    def should_cache(self, value: Any) -> bool:
        return True

    @override
    def ttl_for(self, value: Any, default_ttl_seconds: int) -> int:
        return self.none_ttl_seconds if value is None else default_ttl_seconds


DEFAULT_NULL_VALUE_STRATEGY: RedisCacheStrategy = RedisSkipNone()
DEFAULT_SKIP_NONE_STRATEGY: RedisCacheStrategy = DEFAULT_NULL_VALUE_STRATEGY
DEFAULT_CACHE_ALL_STRATEGY: RedisCacheStrategy = RedisCacheAll()
DEFAULT_TTL_NONE_STRATEGY: RedisCacheStrategy = RedisTTLNone(1)


def _apply_prefix(key: str, key_prefix: str) -> str:
    if not key_prefix:
        return key
    return key if key.startswith(key_prefix) else f"{key_prefix}{key}"


def _batch_apply_prefix(keys: list[str] | tuple[str, ...], key_prefix: str) -> list[str]:
    if not key_prefix:
        return list(keys)
    return [k if k.startswith(key_prefix) else f"{key_prefix}{k}" for k in keys]


def build_cache_key(prefix: str, *parts: Any, sep: str = ":") -> str:
    str_parts = [str(p) for p in parts if p is not None]
    return sep.join([prefix, *str_parts]) if str_parts else prefix


class AsyncRedisPrefixedOp:
    def __init__(
        self,
        redis: Redis,
        key_prefix: str,
        *,
        logger: FilteringBoundLogger | None = None,
    ) -> None:
        self.redis = redis
        self.key_prefix = key_prefix
        self.logger = logger or _DEFAULT_LOGGER

    def get_real_key(self, key: str) -> str:
        return _apply_prefix(key, self.key_prefix)

    async def get(
        self,
        key: str,
        default: T | None = None,
        *,
        serializer: SerializationMode = SerializationMode.NONE,
    ) -> T | None:
        try:
            value = await self.redis.get(_apply_prefix(key, self.key_prefix))
            if value is None:
                return default
            return self._deserialize(value, serializer)
        except RedisError as exc:
            self.logger.warning("Redis get error", key=key, error=str(exc))
            return default

    async def set(
        self,
        key: str,
        value: Any,
        expire: int | timedelta | None = None,
        nx: bool = False,
        xx: bool = False,
        *,
        serializer: SerializationMode = SerializationMode.NONE,
    ) -> bool:
        try:
            serialized_value = self._serialize(value, serializer)

            expire_seconds: int | None = None
            if isinstance(expire, timedelta):
                expire_seconds = int(expire.total_seconds())
            elif isinstance(expire, int):
                expire_seconds = expire

            result = await self.redis.set(
                _apply_prefix(key, self.key_prefix),
                serialized_value,
                ex=expire_seconds,
                nx=nx,
                xx=xx,
            )
            return bool(result)
        except RedisError as exc:
            self.logger.warning("Redis set error", key=key, error=str(exc))
            return False

    async def delete(self, *keys: str) -> int:
        try:
            prefixed = _batch_apply_prefix(list(keys), self.key_prefix)
            return await self.redis.delete(*prefixed)
        except RedisError as exc:
            self.logger.warning("Redis delete error", keys=keys, error=str(exc))
            return 0

    async def exists(self, *keys: str) -> int:
        try:
            prefixed = _batch_apply_prefix(list(keys), self.key_prefix)
            return await self.redis.exists(*prefixed)
        except RedisError as exc:
            self.logger.warning("Redis exists error", keys=keys, error=str(exc))
            return 0

    async def expire(self, key: str, seconds: int | timedelta) -> bool:
        try:
            expire_seconds = int(seconds.total_seconds()) if isinstance(seconds, timedelta) else int(seconds)
            return await self.redis.expire(_apply_prefix(key, self.key_prefix), expire_seconds)
        except RedisError as exc:
            self.logger.warning("Redis expire error", key=key, error=str(exc))
            return False

    async def ttl(self, key: str) -> int:
        try:
            return await self.redis.ttl(_apply_prefix(key, self.key_prefix))
        except RedisError as exc:
            self.logger.warning("Redis ttl error", key=key, error=str(exc))
            return -1

    async def cache_get_or_set(
        self,
        key: str,
        producer: Callable[[], Awaitable[Any]],
        *,
        ttl: int | timedelta = 300,
        serializer: SerializationMode = SerializationMode.JSON,
        null_value_strategy: RedisCacheStrategy = DEFAULT_NULL_VALUE_STRATEGY,
        force_call_producer: bool = False,
    ) -> Any:
        prefixed_key = _apply_prefix(key, self.key_prefix)
        if not force_call_producer:
            raw = await self.redis.get(prefixed_key)
            if raw is not None:
                return self._deserialize(raw, serializer)

        value = await producer()

        default_expire_seconds: int = int(ttl.total_seconds()) if isinstance(ttl, timedelta) else int(ttl)

        strategy: RedisCacheStrategy = null_value_strategy
        if not strategy.should_cache(value):
            return value
        expire_seconds = strategy.ttl_for(value, default_expire_seconds)

        _ = await self.set(key, value, expire=expire_seconds, serializer=serializer)
        return value

    async def throttle_check_and_set(
        self,
        key: str,
        window_seconds: int,
        *,
        value: str = "1",
    ) -> DebounceResult:
        """节流检查: 在时间窗口内只允许第一次请求通过

        Args:
            key: Redis 键
            window_seconds: 时间窗口(秒)
            value: 存储的值

        Returns:
            DebounceResult: 包含是否允许、剩余时间等信息
        """
        prefixed_key = _apply_prefix(key, self.key_prefix)

        try:
            was_set = await self.redis.set(
                prefixed_key,
                value,
                ex=window_seconds,
                nx=True,
            )

            if was_set:
                return DebounceResult(
                    allowed=True,
                    remaining_seconds=0.0,
                    redis_key=prefixed_key,
                )

            ttl = await self.redis.ttl(prefixed_key)
            remaining_seconds = max(0.0, float(ttl)) if ttl > 0 else 0.0

            return DebounceResult(
                allowed=False,
                remaining_seconds=remaining_seconds,
                redis_key=prefixed_key,
            )
        except RedisError as exc:
            self.logger.warning("Redis throttle_check_and_set error", key=key, error=str(exc))
            return DebounceResult(
                allowed=True,
                remaining_seconds=0.0,
                redis_key=prefixed_key,
            )

    async def debounce_check_and_set(
        self,
        key: str,
        window_seconds: int,
        *,
        value: str = "1",
    ) -> DebounceResult:
        """防抖检查(实际上是节流的另一种实现)

        注意: 此方法的命名可能有误导性.它实际上实现的是节流(throttle)逻辑:
        - 如果键不存在,设置键并允许
        - 如果键存在,拒绝并返回剩余时间

        Args:
            key: Redis 键
            window_seconds: 时间窗口(秒)
            value: 存储的值

        Returns:
            DebounceResult: 包含是否允许、剩余时间等信息
        """
        prefixed_key = _apply_prefix(key, self.key_prefix)

        try:
            was_set = await self.redis.set(
                prefixed_key,
                value,
                ex=window_seconds,
                nx=True,
            )

            if was_set:
                return DebounceResult(
                    allowed=True,
                    remaining_seconds=0.0,
                    redis_key=prefixed_key,
                )

            ttl = await self.redis.ttl(prefixed_key)
            remaining_seconds = max(0.0, float(ttl)) if ttl > 0 else 0.0

            return DebounceResult(
                allowed=False,
                remaining_seconds=remaining_seconds,
                redis_key=prefixed_key,
            )
        except RedisError as exc:
            self.logger.warning("Redis debounce_check_and_set error", key=key, error=str(exc))
            return DebounceResult(
                allowed=True,
                remaining_seconds=0.0,
                redis_key=prefixed_key,
            )

    async def debounce_get_remaining(self, key: str) -> DebounceResult:
        prefixed_key = _apply_prefix(key, self.key_prefix)

        try:
            exists = await self.redis.exists(prefixed_key)

            if not exists:
                return DebounceResult(
                    allowed=True,
                    remaining_seconds=0.0,
                    redis_key=prefixed_key,
                )

            ttl = await self.redis.ttl(prefixed_key)
            remaining_seconds = max(0.0, float(ttl)) if ttl > 0 else 0.0

            return DebounceResult(
                allowed=remaining_seconds == 0.0,
                remaining_seconds=remaining_seconds,
                redis_key=prefixed_key,
            )
        except RedisError as exc:
            self.logger.warning("Redis debounce_get_remaining error", key=key, error=str(exc))
            return DebounceResult(
                allowed=True,
                remaining_seconds=0.0,
                redis_key=prefixed_key,
            )

    async def debounce_action(
        self,
        action: str,
        window_seconds: int,
        *,
        group_by: str | list[str] | None = None,
    ) -> DebounceResult:
        key_parts = ["debounce", action]

        if group_by:
            if isinstance(group_by, str):
                key_parts.append(group_by)
            elif isinstance(group_by, list):
                key_parts.extend(group_by)

        key = ":".join(key_parts)

        return await self.debounce_check_and_set(key, window_seconds)

    def async_cached_with(
        self,
        key_builder: Callable[P, str],
        *,
        ttl: int | timedelta = 300,
        serializer: SerializationMode = SerializationMode.JSON,
        null_value_strategy: RedisCacheStrategy = DEFAULT_NULL_VALUE_STRATEGY,
    ) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
        def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                key = key_builder(*args, **kwargs)
                return await self.cache_get_or_set(
                    key,
                    lambda: func(*args, **kwargs),
                    ttl=ttl,
                    serializer=serializer,
                    null_value_strategy=null_value_strategy,
                )

            return wrapper

        return decorator

    async def get_json(self, key: str, default: T | None = None) -> T | None:
        try:
            value = await self.redis.get(_apply_prefix(key, self.key_prefix))
            if value is None:
                return default

            if isinstance(value, bytes):
                value = value.decode("utf-8")
            elif not isinstance(value, str):
                value = str(value)

            return json.loads(value)
        except (RedisError, json.JSONDecodeError) as exc:
            self.logger.warning("Redis get_json error", key=key, error=str(exc))
            return default

    async def set_json(
        self,
        key: str,
        value: Any,
        expire_seconds: int | timedelta | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        try:
            json_value = json.dumps(value, ensure_ascii=False)

            expire_sec: int | None = None
            if isinstance(expire_seconds, timedelta):
                expire_sec = int(expire_seconds.total_seconds())
            elif isinstance(expire_seconds, int):
                expire_sec = expire_seconds

            result = await self.redis.set(
                _apply_prefix(key, self.key_prefix),
                json_value,
                ex=expire_sec,
                nx=nx,
                xx=xx,
            )
            return bool(result)
        except (RedisError, TypeError, ValueError) as exc:
            self.logger.warning("Redis set_json error", key=key, error=str(exc))
            return False

    async def hget(
        self,
        key: str,
        field: str,
        default: T | None = None,
        *,
        serializer: SerializationMode = SerializationMode.NONE,
    ) -> T | None:
        try:
            value = await self.redis.hget(_apply_prefix(key, self.key_prefix), field)  # pyright: ignore[reportGeneralTypeIssues, reportUnknownVariableType]
            if value is None:
                return default
            return self._deserialize(value, serializer)  # pyright: ignore[reportUnknownArgumentType]
        except RedisError as exc:
            self.logger.warning("Redis hget error", key=key, field=field, error=str(exc))
            return default

    async def hset(
        self,
        key: str,
        field: str,
        value: Any,
        *,
        serializer: SerializationMode = SerializationMode.NONE,
    ) -> bool:
        try:
            serialized_value = self._serialize(value, serializer)
            result = await self.redis.hset(_apply_prefix(key, self.key_prefix), field, serialized_value)  # pyright: ignore[reportGeneralTypeIssues, reportUnknownVariableType, reportUnknownMemberType]
            return bool(result)  # pyright: ignore[reportUnknownArgumentType]
        except RedisError as exc:
            self.logger.warning("Redis hset error", key=key, field=field, error=str(exc))
            return False

    async def hgetall(
        self,
        key: str,
        *,
        serializer: SerializationMode = SerializationMode.NONE,
    ) -> dict[str, Any]:
        try:
            data = await self.redis.hgetall(_apply_prefix(key, self.key_prefix))  # pyright: ignore[reportGeneralTypeIssues, reportUnknownMemberType, reportUnknownVariableType]
            return {k: self._deserialize(v, serializer) for k, v in data.items()}  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType, reportUnknownMemberType]
        except RedisError as exc:
            self.logger.warning("Redis hgetall error", key=key, error=str(exc))
            return {}

    async def lpush(
        self,
        key: str,
        *values: Any,
        serializer: SerializationMode = SerializationMode.NONE,
    ) -> int:
        try:
            serialized_values = [self._serialize(v, serializer) for v in values]
            return await self.redis.lpush(_apply_prefix(key, self.key_prefix), *serialized_values)  # pyright: ignore[reportGeneralTypeIssues, reportUnknownVariableType]
        except RedisError as exc:
            self.logger.warning("Redis lpush error", key=key, error=str(exc))
            return 0

    async def rpush(
        self,
        key: str,
        *values: Any,
        serializer: SerializationMode = SerializationMode.NONE,
    ) -> int:
        try:
            serialized_values = [self._serialize(v, serializer) for v in values]
            return await self.redis.rpush(_apply_prefix(key, self.key_prefix), *serialized_values)  # pyright: ignore[reportGeneralTypeIssues, reportUnknownVariableType]
        except RedisError as exc:
            self.logger.warning("Redis rpush error", key=key, error=str(exc))
            return 0

    async def lpop(
        self,
        key: str,
        default: list[T] | T | None = None,
        *,
        count: int | None = None,
        serializer: SerializationMode = SerializationMode.NONE,
    ) -> list[T] | T | None:
        try:
            value = await self.redis.lpop(_apply_prefix(key, self.key_prefix), count=count)  # pyright: ignore[reportGeneralTypeIssues, reportUnknownMemberType, reportUnknownVariableType]
            if value is None:
                return default
            if isinstance(value, list):
                return [self._deserialize(v, serializer) for v in value]  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
            return self._deserialize(value, serializer)  # pyright: ignore[reportUnknownArgumentType]
        except RedisError as exc:
            self.logger.warning("Redis lpop error", key=key, error=str(exc))
            return default

    async def lrange(
        self,
        key: str,
        start: int = 0,
        end: int = -1,
        *,
        serializer: SerializationMode = SerializationMode.NONE,
    ) -> list[Any]:
        try:
            values = await self.redis.lrange(  # pyright: ignore[reportGeneralTypeIssues, reportUnknownMemberType, reportUnknownVariableType]
                _apply_prefix(key, self.key_prefix),
                start,
                end,
            )
            return [self._deserialize(v, serializer) for v in values]  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
        except RedisError as exc:
            self.logger.warning("Redis lrange error", key=key, error=str(exc))
            return []

    async def sadd(
        self,
        key: str,
        *values: Any,
        serializer: SerializationMode = SerializationMode.NONE,
    ) -> int:
        try:
            serialized_values = [self._serialize(v, serializer) for v in values]
            return await self.redis.sadd(_apply_prefix(key, self.key_prefix), *serialized_values)  # pyright: ignore[reportGeneralTypeIssues, reportUnknownVariableType]
        except RedisError as exc:
            self.logger.warning("Redis sadd error", key=key, error=str(exc))
            return 0

    async def smembers(
        self,
        key: str,
        *,
        serializer: SerializationMode = SerializationMode.NONE,
    ) -> builtins.set[Any]:
        try:
            values = await self.redis.smembers(_apply_prefix(key, self.key_prefix))  # pyright: ignore[reportGeneralTypeIssues, reportUnknownMemberType, reportUnknownVariableType]
            return {self._deserialize(v, serializer) for v in values}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
        except RedisError as exc:
            self.logger.warning("Redis smembers error", key=key, error=str(exc))
            return set()

    async def mget(
        self,
        *keys: str,
        serializer: SerializationMode = SerializationMode.NONE,
    ) -> list[Any | None]:
        try:
            prefixed = _batch_apply_prefix(list(keys), self.key_prefix)
            values = await self.redis.mget(*prefixed)
            return [self._deserialize(v, serializer) if v is not None else None for v in values]
        except RedisError as exc:
            self.logger.warning("Redis mget error", keys=keys, error=str(exc))
            return [None] * len(keys)

    async def mset(
        self,
        mapping: dict[str, Any],
        *,
        serializer: SerializationMode = SerializationMode.NONE,
    ) -> bool:
        try:
            serialized_mapping = {_apply_prefix(k, self.key_prefix): self._serialize(v, serializer) for k, v in mapping.items()}
            return await self.redis.mset(serialized_mapping)
        except RedisError as exc:
            self.logger.warning("Redis mset error", error=str(exc))
            return False

    def _serialize(self, value: Any, mode: SerializationMode) -> Any:
        if mode == SerializationMode.NONE:
            return value
        if mode == SerializationMode.JSON:
            return json.dumps(value, ensure_ascii=False)
        if mode == SerializationMode.STRING:
            return str(value)
        return value

    def _deserialize(self, value: str | bytes | None, mode: SerializationMode) -> Any:
        if value is None:
            return None

        if isinstance(value, bytes):
            value = value.decode("utf-8")
        elif not isinstance(value, str):
            value = str(value)

        if mode == SerializationMode.NONE:
            return value
        if mode == SerializationMode.JSON:
            try:
                return json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                return value
        if mode == SerializationMode.STRING:
            return value
        return value

    @contextlib.asynccontextmanager
    async def simple_distributed_lock(self, lock_key: str, timeout: int) -> AsyncGenerator[bool, None]:
        acquired = False
        try:
            acquired = await self.set(
                key=lock_key,
                value="1",
                expire=timeout,
                nx=True,
            )

            if not acquired:
                self.logger.warning("Unable to acquire distributed lock", lock_key=lock_key)

            yield acquired

        finally:
            if acquired:
                try:
                    _ = await self.delete(lock_key)
                except Exception:
                    self.logger.exception("Failed to release distributed lock", lock_key=lock_key)


class AsyncRedisManager:
    def __init__(
        self,
        *,
        host: str = "localhost",
        port: int = 6379,
        password: str | None = None,
        db: int = 0,
        max_connections: int = 20,
        retry_on_timeout: bool = True,
        socket_keepalive: bool = True,
        socket_keepalive_options: dict[str, Any] | None = None,
        socket_connect_timeout: int = 5,
        socket_timeout: int = 5,
        health_check_interval: int = 30,
        key_prefix: str = "",
        logger: FilteringBoundLogger | None = None,
        **kwargs: Any,
    ) -> None:
        self.key_prefix: str = key_prefix or ""
        self.logger: FilteringBoundLogger = logger or _DEFAULT_LOGGER

        self.pool: ConnectionPool = ConnectionPool(
            host=host,
            port=port,
            password=password,
            db=db,
            max_connections=max_connections,
            retry_on_timeout=retry_on_timeout,
            socket_keepalive=socket_keepalive,
            socket_keepalive_options=socket_keepalive_options or {},
            socket_connect_timeout=socket_connect_timeout,
            socket_timeout=socket_timeout,
            health_check_interval=health_check_interval,
            decode_responses=True,
            **kwargs,
        )

        self.origin_redis_conn: Redis = redis.Redis(connection_pool=self.pool)
        self.op_prefixed: AsyncRedisPrefixedOp = AsyncRedisPrefixedOp(self.origin_redis_conn, key_prefix, logger=self.logger)

        self.connection_info = {
            "host": host,
            "port": port,
            "db": db,
            "max_connections": max_connections,
            "socket_connect_timeout": socket_connect_timeout,
            "socket_timeout": socket_timeout,
            "health_check_interval": health_check_interval,
        }

    async def health_check(self) -> bool:
        try:
            pong = await self.origin_redis_conn.ping()  # pyright: ignore[reportUnknownMemberType]
            return bool(pong == "PONG" or pong is True)
        except Exception:
            self.logger.exception("Redis ping error", connection_info=self.connection_info)
            return False

    async def close(self) -> None:
        with contextlib.suppress(RedisError):
            await self.origin_redis_conn.aclose(close_connection_pool=True)
