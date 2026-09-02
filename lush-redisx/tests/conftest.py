"""共享的 pytest fixtures

目标:
- 连接 docker compose bridge 内的 ``redis`` 服务 (无宿主机端口映射)
- 通过 ``just test-docker lush-redisx`` 运行
- 幂等: 随机 key_prefix, teardown 时清理
"""

from __future__ import annotations

import contextlib
import os
import random
import time
import uuid
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass

import pytest
import redis
import redis.asyncio as redis_async

from lush_redisx import AsyncRedisManager


@dataclass(frozen=True, slots=True)
class _RedisEndpoint:
    host: str
    port: int
    password: str | None
    db: int
    key_prefix: str


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return default if raw is None else int(raw)


def _wait_for_redis_ping(host: str, port: int, *, timeout_s: float = 30.0) -> None:
    client = redis.Redis(host=host, port=port, decode_responses=True)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        with contextlib.suppress(Exception):
            if client.ping():
                return
        time.sleep(0.2)
    raise RuntimeError(
        f"Redis not ready at {host}:{port}. "
        "Start compose infra: just test-docker lush-redisx"
    )


@pytest.fixture(scope="session")
def redis_endpoint() -> Generator[_RedisEndpoint, None, None]:
    host = os.getenv("REDIS_HOST", "redis")
    port = _env_int("REDIS_PORT", 6379)
    password = os.getenv("REDIS_PASSWORD") or None
    db = _env_int("REDIS_DB", random.randint(0, 15))
    key_prefix = f":lush-redisx:test:{uuid.uuid4().hex}:"

    _wait_for_redis_ping(host, port, timeout_s=30.0)
    yield _RedisEndpoint(host=host, port=port, password=password, db=db, key_prefix=key_prefix)


async def _cleanup_redis_keys(endpoint: _RedisEndpoint) -> None:
    if not endpoint.key_prefix:
        return

    match = f"{endpoint.key_prefix}*"
    keys: list[str] = []
    client = redis_async.Redis(
        host=endpoint.host,
        port=endpoint.port,
        password=endpoint.password,
        db=endpoint.db,
        decode_responses=True,
    )
    try:
        async for key in client.scan_iter(match=match, count=1000):  # pyright: ignore[reportUnknownMemberType]
            keys.append(key)
            if len(keys) >= 500:
                _ = await client.delete(*keys)  # pyright: ignore[reportUnknownMemberType]
                keys.clear()
        if keys:
            _ = await client.delete(*keys)  # pyright: ignore[reportUnknownMemberType]
    except Exception:
        return
    finally:
        with contextlib.suppress(Exception):
            await client.aclose(close_connection_pool=True)  # pyright: ignore[reportUnknownMemberType]


@pytest.fixture
async def redis_mgr(redis_endpoint: _RedisEndpoint) -> AsyncGenerator[AsyncRedisManager, None]:
    mgr = AsyncRedisManager(
        host=redis_endpoint.host,
        port=redis_endpoint.port,
        password=redis_endpoint.password,
        db=redis_endpoint.db,
        key_prefix=redis_endpoint.key_prefix,
        max_connections=20,
        retry_on_timeout=True,
    )
    try:
        ok = await mgr.health_check()
        if not ok:
            raise RuntimeError(f"Redis health_check failed: {redis_endpoint.host}:{redis_endpoint.port}")
        yield mgr
    finally:
        await _cleanup_redis_keys(redis_endpoint)
        await mgr.close()
