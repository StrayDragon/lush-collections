"""共享的 pytest fixtures

目标:
- 测试时自动准备 Redis (优先复用本机,不可用则用 Docker 起一个临时实例)
- 幂等: 多次运行不会因残留容器/残留 key 影响结果
- 隔离: 使用随机 key_prefix,并在 teardown 时清理
"""

from __future__ import annotations

import contextlib
import os
import random
import shutil
import socket
import subprocess
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
    container_name: str | None = None


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return default if raw is None else int(raw)


def _tcp_connectable(host: str, port: int, *, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _docker_available() -> bool:
    docker = shutil.which("docker")
    if docker is None:
        return False
    try:
        proc = subprocess.run(  # noqa: S603
            [docker, "ps"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return False
    else:
        return proc.returncode == 0


def _docker_image_exists(image: str) -> bool:
    docker = shutil.which("docker")
    if docker is None:
        return False
    try:
        proc = subprocess.run(  # noqa: S603
            [docker, "image", "inspect", image],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return False
    else:
        return proc.returncode == 0


def _choose_redis_image() -> str:
    # User override
    env_image = os.getenv("LUSH_TEST_REDIS_IMAGE")
    if env_image:
        return env_image

    # Prefer local images to avoid pulling (fast path)
    candidates = [
        "redis:7.4-alpine",
        "redis:7-alpine",
        "redis:7",
        "redis:6-alpine",
        "redis:6",
    ]
    for image in candidates:
        if _docker_image_exists(image):
            return image

    # Fallback: docker will pull if missing
    return "redis:7-alpine"


def _docker_rm_if_exists(container_name: str) -> None:
    docker = shutil.which("docker")
    if docker is None:
        return
    subprocess.run(  # noqa: S603
        [docker, "rm", "-f", container_name],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def _docker_start_redis(container_name: str, image: str) -> int:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("Docker is unavailable")
    _docker_rm_if_exists(container_name)
    subprocess.run(  # noqa: S603
        [
            docker,
            "run",
            "--rm",
            "-d",
            "--name",
            container_name,
            "-p",
            "0:6379",
            image,
            "redis-server",
            "--save",
            "",
            "--appendonly",
            "no",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        text=True,
    )

    # Example output:
    # 0.0.0.0:49153
    # :::49153
    port_line = subprocess.check_output([docker, "port", container_name, "6379/tcp"], text=True).strip().splitlines()[0]  # noqa: S603
    return int(port_line.rsplit(":", maxsplit=1)[-1])


def _wait_for_redis_ping(host: str, port: int, *, timeout_s: float = 15.0) -> None:
    client = redis.Redis(host=host, port=port, decode_responses=True)
    deadline = time.time() + timeout_s
    while True:
        with contextlib.suppress(Exception):
            if client.ping():
                return

        if time.time() >= deadline:
            raise RuntimeError(f"Redis still not ready: {host}:{port}")
        time.sleep(0.2)


@pytest.fixture(scope="session")
def redis_endpoint() -> Generator[_RedisEndpoint, None, None]:
    host = os.getenv("REDIS_HOST", "127.0.0.1")
    port = _env_int("REDIS_PORT", 6379)
    password = os.getenv("REDIS_PASSWORD") or None
    db = _env_int("REDIS_DB", random.randint(0, 15))
    key_prefix = f":lush-redisx:test:{uuid.uuid4().hex}:"

    # 1) Prefer existing redis (fast path)
    if _tcp_connectable(host, port):
        with contextlib.suppress(Exception):
            _wait_for_redis_ping(host, port, timeout_s=1.0)
            yield _RedisEndpoint(host=host, port=port, password=password, db=db, key_prefix=key_prefix)
            return

    # 2) Fallback: bring up a temporary container
    if not _docker_available():
        raise RuntimeError(
            "Redis is not reachable and Docker is unavailable. "
            "Start Redis or enable Docker, or set REDIS_HOST/REDIS_PORT to a reachable instance."
        )

    image = _choose_redis_image()
    container_name = os.getenv("LUSH_TEST_REDIS_CONTAINER", f"lush-redisx-pytest-{uuid.uuid4().hex[:10]}")
    docker_port = _docker_start_redis(container_name, image=image)
    try:
        _wait_for_redis_ping("127.0.0.1", docker_port, timeout_s=15.0)
        yield _RedisEndpoint(
            host="127.0.0.1",
            port=docker_port,
            password=None,
            db=db,
            key_prefix=key_prefix,
            container_name=container_name,
        )
    finally:
        _docker_rm_if_exists(container_name)


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
        # best effort cleanup; tests should not fail at teardown
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
