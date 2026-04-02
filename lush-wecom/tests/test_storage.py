from __future__ import annotations

import time as _time

import pytest

from lush_wecom.core.storage import AsyncMemoryStorage, AsyncRedisStorage, MemoryStorage, RedisStorage


def test_memory_storage_get_set_and_expire(monkeypatch: pytest.MonkeyPatch) -> None:
    storage = MemoryStorage()
    assert storage.get("missing") is None

    t0 = 100.0
    monkeypatch.setattr(_time, "time", lambda: t0)
    storage.set("k", "v", expires_in=1)
    assert storage.get("k") == "v"

    # Advance time so the key is expired; get() should delete and return None.
    monkeypatch.setattr(_time, "time", lambda: t0 + 2.0)
    assert storage.get("k") is None
    assert storage.get("k") is None


def test_redis_storage_get_set_calls_client() -> None:
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
    store: dict[str, str] = {}

    class _Redis:
        def get(self, key: str) -> str | None:
            calls.append(("get", (key,), {}))
            return store.get(key)

        def set(self, key: str, value: str, *, ex: int) -> None:
            calls.append(("set", (key, value), {"ex": ex}))
            store[key] = value

    storage = RedisStorage(_Redis())  # type: ignore[arg-type]
    assert storage.get("k") is None
    storage.set("k", "v", expires_in=1)
    assert storage.get("k") == "v"

    assert calls[0][0] == "get"
    assert calls[1][0] == "set"
    assert calls[2][0] == "get"


@pytest.mark.asyncio
async def test_async_memory_storage_get_set_and_expire(monkeypatch: pytest.MonkeyPatch) -> None:
    storage = AsyncMemoryStorage()
    assert await storage.get("missing") is None

    t0 = 200.0
    monkeypatch.setattr(_time, "time", lambda: t0)
    await storage.set("k", "v", expires_in=1)
    assert await storage.get("k") == "v"

    monkeypatch.setattr(_time, "time", lambda: t0 + 2.0)
    assert await storage.get("k") is None
    assert await storage.get("k") is None


@pytest.mark.asyncio
async def test_async_redis_storage_get_set_calls_client() -> None:
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
    store: dict[str, str] = {}

    class _AsyncRedis:
        async def get(self, key: str) -> str | None:
            calls.append(("get", (key,), {}))
            return store.get(key)

        async def set(self, key: str, value: str, *, ex: int) -> None:
            calls.append(("set", (key, value), {"ex": ex}))
            store[key] = value

    storage = AsyncRedisStorage(_AsyncRedis())  # type: ignore[arg-type]
    assert await storage.get("k") is None
    await storage.set("k", "v", expires_in=1)
    assert await storage.get("k") == "v"

    assert calls[0][0] == "get"
    assert calls[1][0] == "set"
    assert calls[2][0] == "get"
