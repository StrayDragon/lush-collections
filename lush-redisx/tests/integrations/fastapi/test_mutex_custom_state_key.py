"""测试互斥锁自定义 state_key 的场景."""  # noqa: INP001

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from lush_redisx import AsyncRedisManager
from lush_redisx.integrations.fastapi.depends import MutexGuard
from lush_redisx.integrations.fastapi.depends.mutex import create_mutex_auto_release_middleware


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


def test_custom_state_key(fake_redis: FakeRedisManager) -> None:
    """测试使用自定义 state_key."""
    app = FastAPI()

    # 使用自定义字段名
    custom_state_key = "_my_custom_locks"

    # 创建对应的中间件
    custom_middleware = create_mutex_auto_release_middleware(lambda req: getattr(req.state, custom_state_key, []))
    app.add_middleware(custom_middleware)

    async def get_redis() -> AsyncRedisManager:
        return fake_redis

    # 创建使用自定义 state_key 的互斥守卫
    mutex = MutexGuard(
        timeout_seconds=30,
        redis_dependency=get_redis,
        action="custom_action",
        state_key=custom_state_key,
    )

    @app.post("/test")
    async def test_endpoint(
        _mutex: Annotated[None, Depends(mutex)],
    ) -> dict:
        return {"status": "ok"}

    client = TestClient(app)
    response = client.post("/test")

    # 请求应该成功
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    # 锁应该被释放
    assert len(fake_redis.locks) == 0, "所有锁应该被释放"
    assert len(fake_redis.deleted_keys) == 1


def test_multiple_mutex_guards_with_different_state_keys(fake_redis: FakeRedisManager) -> None:
    """测试在同一个应用中使用不同的 state_key."""
    app = FastAPI()

    # 定义两个不同的 state_key
    state_key_1 = "_locks_group_1"
    state_key_2 = "_locks_group_2"

    # 创建两个中间件
    middleware_1 = create_mutex_auto_release_middleware(lambda req: getattr(req.state, state_key_1, []))
    middleware_2 = create_mutex_auto_release_middleware(lambda req: getattr(req.state, state_key_2, []))

    app.add_middleware(middleware_1)
    app.add_middleware(middleware_2)

    async def get_redis() -> AsyncRedisManager:
        return fake_redis

    # 创建两个使用不同 state_key 的互斥守卫
    mutex_1 = MutexGuard(
        timeout_seconds=30,
        redis_dependency=get_redis,
        action="action1",
        state_key=state_key_1,
    )

    mutex_2 = MutexGuard(
        timeout_seconds=30,
        redis_dependency=get_redis,
        action="action2",
        state_key=state_key_2,
    )

    @app.post("/test")
    async def test_endpoint(
        _mutex1: Annotated[None, Depends(mutex_1)],
        _mutex2: Annotated[None, Depends(mutex_2)],
    ) -> dict:
        return {"status": "ok"}

    client = TestClient(app)
    response = client.post("/test")

    # 请求应该成功
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    # 所有锁应该被释放
    assert len(fake_redis.locks) == 0, "所有锁应该被释放"
    assert len(fake_redis.deleted_keys) == 2


def test_custom_state_key_with_exception(fake_redis: FakeRedisManager) -> None:
    """测试自定义 state_key 在异常时也能正确释放锁."""
    app = FastAPI()

    custom_state_key = "_my_locks"
    custom_middleware = create_mutex_auto_release_middleware(lambda req: getattr(req.state, custom_state_key, []))
    app.add_middleware(custom_middleware)

    async def get_redis() -> AsyncRedisManager:
        return fake_redis

    mutex = MutexGuard(
        timeout_seconds=30,
        redis_dependency=get_redis,
        action="action",
        state_key=custom_state_key,
    )

    @app.post("/test")
    async def test_endpoint(
        _mutex: Annotated[None, Depends(mutex)],
    ) -> dict:
        raise ValueError("Test exception")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/test")

    # 请求应该失败
    assert response.status_code == 500

    # 即使发生异常,锁也应该被释放
    assert len(fake_redis.locks) == 0, "所有锁应该被释放"
    assert len(fake_redis.deleted_keys) == 1
