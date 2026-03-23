from __future__ import annotations

import asyncio
import time

import pytest

from lush_redisx import (
    DEFAULT_CACHE_ALL_STRATEGY,
    AsyncRedisPrefixedOp,
    RedisSkipNone,
    SerializationMode,
    build_cache_key,
)


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.expiry: dict[str, float] = {}

    def _now(self) -> float:
        return time.monotonic()

    def _purge_if_expired(self, key: str) -> None:
        expire_at = self.expiry.get(key)
        if expire_at is not None and expire_at <= self._now():
            self.store.pop(key, None)
            self.expiry.pop(key, None)

    async def get(self, key: str) -> str | None:
        self._purge_if_expired(key)
        return self.store.get(key)

    async def set(
        self,
        key: str,
        value: str,
        *,
        ex: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        self._purge_if_expired(key)
        exists = key in self.store
        if nx and exists:
            return False
        if xx and not exists:
            return False
        self.store[key] = value
        if ex is not None:
            self.expiry[key] = self._now() + ex
        else:
            self.expiry.pop(key, None)
        return True

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            self._purge_if_expired(key)
            if key in self.store:
                deleted += 1
            self.store.pop(key, None)
            self.expiry.pop(key, None)
        return deleted

    async def exists(self, *keys: str) -> int:
        count = 0
        for key in keys:
            self._purge_if_expired(key)
            if key in self.store:
                count += 1
        return count

    async def ttl(self, key: str) -> int:
        self._purge_if_expired(key)
        expire_at = self.expiry.get(key)
        if key not in self.store:
            return -2
        if expire_at is None:
            return -1
        remaining = expire_at - self._now()
        return int(remaining) if remaining > 0 else -2


@pytest.fixture
def redis_op() -> AsyncRedisPrefixedOp:
    fake = FakeRedis()
    return AsyncRedisPrefixedOp(fake, ":test:")


@pytest.mark.asyncio
async def test_build_cache_key() -> None:
    assert build_cache_key(":cache:", "user", 1) == ":cache::user:1"


@pytest.mark.asyncio
async def test_cache_get_or_set(redis_op: AsyncRedisPrefixedOp) -> None:
    calls = 0

    async def producer() -> str:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return "value"

    value = await redis_op.cache_get_or_set("key", producer)
    assert value == "value"
    cached = await redis_op.cache_get_or_set("key", producer)
    assert cached == "value"
    assert calls == 1


@pytest.mark.asyncio
async def test_async_cached_with(redis_op: AsyncRedisPrefixedOp) -> None:
    calls = 0

    @redis_op.async_cached_with(
        lambda x: f"fn:{x}", ttl=30, serializer=SerializationMode.STRING, null_value_strategy=DEFAULT_CACHE_ALL_STRATEGY
    )
    async def echo(x: str) -> str:
        nonlocal calls
        calls += 1
        return x.upper()

    assert await echo("hi") == "HI"
    assert await echo("hi") == "HI"
    assert calls == 1


@pytest.mark.asyncio
async def test_debounce_action(redis_op: AsyncRedisPrefixedOp) -> None:
    first = await redis_op.debounce_action("task", window_seconds=2)
    assert first.allowed is True
    second = await redis_op.debounce_action("task", window_seconds=2)
    assert second.allowed is False
    assert second.remaining_seconds >= 0


@pytest.mark.asyncio
async def test_simple_distributed_lock(redis_op: AsyncRedisPrefixedOp) -> None:
    async with redis_op.simple_distributed_lock("lock", timeout=5) as acquired:
        assert acquired is True
        async with redis_op.simple_distributed_lock("lock", timeout=5) as second:
            assert second is False


@pytest.mark.asyncio
async def test_set_get_json(redis_op: AsyncRedisPrefixedOp) -> None:
    await redis_op.set_json("json", {"a": 1})
    data = await redis_op.get_json("json")
    assert data == {"a": 1}


@pytest.mark.asyncio
async def test_cache_strategy_skip_none(redis_op: AsyncRedisPrefixedOp) -> None:
    calls = 0

    async def producer() -> None:
        nonlocal calls
        calls += 1

    result = await redis_op.cache_get_or_set(
        "maybe-none",
        producer,
        serializer=SerializationMode.STRING,
        null_value_strategy=RedisSkipNone(),
    )
    assert result is None
    assert calls == 1
    cached = await redis_op.cache_get_or_set(
        "maybe-none",
        producer,
        serializer=SerializationMode.STRING,
        null_value_strategy=RedisSkipNone(),
    )
    assert cached is None
    assert calls == 2
