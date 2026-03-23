"""测试互斥锁中间件支持多个锁的场景."""  # noqa: INP001

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from lush_redisx import AsyncRedisManager
from lush_redisx.integrations.fastapi.depends import MutexGuard
from lush_redisx.integrations.fastapi.middleware import MutexReleaseMiddleware


class FakeRedisManager:
    """假的 Redis 管理器用于测试."""

    def __init__(self) -> None:
        self.deleted_keys: list[str] = []
        self.locks: dict[str, bool] = {}

    @property
    def op_prefixed(self) -> "FakeRedisManager":
        return self

    async def set(self, key: str, value: str, expire: int, nx: bool) -> bool:
        """模拟设置锁."""
        if nx and key in self.locks:
            return False
        self.locks[key] = True
        return True

    async def delete(self, key: str) -> int:
        """模拟删除锁."""
        self.deleted_keys.append(key)
        if key in self.locks:
            del self.locks[key]
            return 1
        return 0


@pytest.fixture
def fake_redis() -> FakeRedisManager:
    """创建假的 Redis 管理器."""
    return FakeRedisManager()


def test_multiple_locks_in_single_request(fake_redis: FakeRedisManager) -> None:
    """测试单个请求中获取多个锁."""
    app = FastAPI()
    app.add_middleware(MutexReleaseMiddleware)

    async def get_redis() -> AsyncRedisManager:
        return fake_redis

    # 创建两个不同的互斥守卫
    mutex1 = MutexGuard(
        timeout_seconds=30,
        redis_dependency=get_redis,
        action="action1",
    )

    mutex2 = MutexGuard(
        timeout_seconds=30,
        redis_dependency=get_redis,
        action="action2",
    )

    @app.post("/test")
    async def test_endpoint(
        _mutex1: Annotated[None, Depends(mutex1)],
        _mutex2: Annotated[None, Depends(mutex2)],
    ) -> dict:
        return {"status": "ok"}

    client = TestClient(app)
    response = client.post("/test")

    # 请求应该成功
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    # 应该获取了两个锁
    assert len(fake_redis.locks) == 0, "所有锁应该被释放"

    # 应该按照逆序释放锁(LIFO)
    assert len(fake_redis.deleted_keys) == 2
    # 第二个锁先释放,第一个锁后释放
    assert "action2" in fake_redis.deleted_keys[0]
    assert "action1" in fake_redis.deleted_keys[1]


def test_multiple_locks_release_on_exception(fake_redis: FakeRedisManager) -> None:
    """测试异常时也能释放所有锁."""
    app = FastAPI()
    app.add_middleware(MutexReleaseMiddleware)

    async def get_redis() -> AsyncRedisManager:
        return fake_redis

    mutex1 = MutexGuard(
        timeout_seconds=30,
        redis_dependency=get_redis,
        action="action1",
    )

    mutex2 = MutexGuard(
        timeout_seconds=30,
        redis_dependency=get_redis,
        action="action2",
    )

    @app.post("/test")
    async def test_endpoint(
        _mutex1: Annotated[None, Depends(mutex1)],
        _mutex2: Annotated[None, Depends(mutex2)],
    ) -> dict:
        raise ValueError("Test exception")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/test")

    # 请求应该失败
    assert response.status_code == 500

    # 即使发生异常,所有锁也应该被释放
    assert len(fake_redis.locks) == 0, "所有锁应该被释放"
    assert len(fake_redis.deleted_keys) == 2


def test_partial_lock_acquisition(fake_redis: FakeRedisManager) -> None:
    """测试部分锁获取失败的场景."""
    app = FastAPI()
    app.add_middleware(MutexReleaseMiddleware)

    async def get_redis() -> AsyncRedisManager:
        return fake_redis

    mutex1 = MutexGuard(
        timeout_seconds=30,
        redis_dependency=get_redis,
        action="action1",
    )

    mutex2 = MutexGuard(
        timeout_seconds=30,
        redis_dependency=get_redis,
        action="action2",
    )

    @app.post("/test")
    async def test_endpoint(
        _mutex1: Annotated[None, Depends(mutex1)],
        _mutex2: Annotated[None, Depends(mutex2)],
    ) -> dict:
        return {"status": "ok"}

    client = TestClient(app, raise_server_exceptions=False)

    # 第一次请求成功
    response1 = client.post("/test")
    assert response1.status_code == 200
    fake_redis.deleted_keys.clear()

    # 手动设置第一个锁已被占用(使用正确的键名)
    fake_redis.locks["mutex:action1:ip:testclient"] = True

    # 第二次请求应该在第一个锁处失败
    response2 = client.post("/test")
    assert response2.status_code == 409  # Conflict

    # 不应该有锁被释放(因为没有成功获取)
    assert len(fake_redis.deleted_keys) == 0
