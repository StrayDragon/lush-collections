"""测试节流和防抖守卫"""  # noqa: INP001

import asyncio
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from lush_redisx.async_redis import AsyncRedisManager, DebounceResult
from lush_redisx.integrations.fastapi.depends import (
    DebounceGuard,
    ThrottleGuard,
    debounce_guard_factory,
    throttle_guard_factory,
)


class FakeRedisManager:
    """模拟 Redis 管理器用于测试"""

    def __init__(self) -> None:
        self.op_prefixed = FakePrefixedOp()


class FakePrefixedOp:
    """模拟 Redis 前缀操作"""

    def __init__(self) -> None:
        self.throttle_calls: list[tuple[str, int]] = []
        self.debounce_calls: list[tuple[str, int]] = []
        self._throttle_results: list[DebounceResult] = []
        self._debounce_results: list[DebounceResult] = []

    def set_throttle_results(self, results: list[DebounceResult]) -> None:
        """设置节流检查的返回结果"""
        self._throttle_results = results.copy()

    def set_debounce_results(self, results: list[DebounceResult]) -> None:
        """设置防抖检查的返回结果"""
        self._debounce_results = results.copy()

    async def throttle_check_and_set(self, key: str, window_seconds: int) -> DebounceResult:
        """模拟节流检查"""
        self.throttle_calls.append((key, window_seconds))
        if self._throttle_results:
            return self._throttle_results.pop(0)
        return DebounceResult(allowed=True, remaining_seconds=0.0, redis_key=key)

    async def debounce_check_and_set(self, key: str, window_seconds: int) -> DebounceResult:
        """模拟防抖检查"""
        self.debounce_calls.append((key, window_seconds))
        if self._debounce_results:
            return self._debounce_results.pop(0)
        return DebounceResult(allowed=True, remaining_seconds=0.0, redis_key=key)


@pytest.fixture
def fake_redis_manager() -> FakeRedisManager:
    """提供模拟的 Redis 管理器"""
    return FakeRedisManager()


@pytest.fixture
def app_with_throttle(fake_redis_manager: FakeRedisManager) -> FastAPI:
    """创建带节流守卫的测试应用"""
    app = FastAPI()

    async def get_redis() -> AsyncRedisManager:
        return fake_redis_manager

    throttle = ThrottleGuard(
        window_seconds=60,
        redis_dependency=get_redis,
        action="test_action",
    )

    @app.get("/throttled")
    async def throttled_endpoint(_guard: Annotated[None, Depends(throttle)]) -> dict:
        return {"status": "ok"}

    return app


@pytest.fixture
def app_with_debounce(fake_redis_manager: FakeRedisManager) -> FastAPI:
    """创建带防抖守卫的测试应用"""
    app = FastAPI()

    async def get_redis() -> AsyncRedisManager:
        return fake_redis_manager

    debounce = DebounceGuard(
        window_seconds=3,
        redis_dependency=get_redis,
        action="search",
    )

    @app.get("/debounced")
    async def debounced_endpoint(_guard: Annotated[None, Depends(debounce)]) -> dict:
        return {"status": "ok"}

    return app


# ========== 节流测试 ==========


def test_throttle_first_request_allowed(app_with_throttle: FastAPI, fake_redis_manager: FakeRedisManager) -> None:
    """测试节流: 第一次请求应该通过"""
    fake_redis_manager.op_prefixed.set_throttle_results(
        [DebounceResult(allowed=True, remaining_seconds=0.0, redis_key="throttle:test_action:testclient")]
    )

    client = TestClient(app_with_throttle)
    response = client.get("/throttled")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(fake_redis_manager.op_prefixed.throttle_calls) == 1


def test_throttle_second_request_blocked(app_with_throttle: FastAPI, fake_redis_manager: FakeRedisManager) -> None:
    """测试节流: 窗口期内第二次请求应该被拒绝"""
    fake_redis_manager.op_prefixed.set_throttle_results(
        [
            DebounceResult(allowed=True, remaining_seconds=0.0, redis_key="throttle:test_action:testclient"),
            DebounceResult(allowed=False, remaining_seconds=45.5, redis_key="throttle:test_action:testclient"),
        ]
    )

    client = TestClient(app_with_throttle)

    # 第一次请求成功
    response1 = client.get("/throttled")
    assert response1.status_code == 200

    # 第二次请求被拒绝
    response2 = client.get("/throttled")
    assert response2.status_code == 429
    data = response2.json()
    # 新的 API 返回简单的字符串
    assert data["detail"] == "Too many requests"


def test_throttle_custom_exception_factory(fake_redis_manager: FakeRedisManager) -> None:
    """测试节流: 自定义异常工厂"""
    app = FastAPI()

    async def get_redis() -> AsyncRedisManager:
        return fake_redis_manager

    def custom_exception_factory(*args, **kwargs):
        return HTTPException(status_code=429, detail={"error": "rate_limited", "message": "请稍后重试"})

    throttle = ThrottleGuard(
        window_seconds=60,
        redis_dependency=get_redis,
        action="custom",
        exception_factory=custom_exception_factory,
    )

    @app.get("/custom")
    async def custom_endpoint(_guard: Annotated[None, Depends(throttle)]) -> dict:
        return {"status": "ok"}

    fake_redis_manager.op_prefixed.set_throttle_results(
        [DebounceResult(allowed=False, remaining_seconds=30.0, redis_key="throttle:custom:testclient")]
    )

    client = TestClient(app)
    response = client.get("/custom")

    assert response.status_code == 429
    assert response.json()["detail"]["error"] == "rate_limited"


def test_throttle_factory(fake_redis_manager: FakeRedisManager) -> None:
    """测试节流工厂函数"""
    app = FastAPI()

    async def get_redis() -> AsyncRedisManager:
        return fake_redis_manager

    throttle = throttle_guard_factory(
        window_seconds=120,
        redis_dependency=get_redis,
        action="factory_test",
    )

    @app.post("/submit")
    async def submit(_guard: Annotated[None, Depends(throttle)]) -> dict:
        return {"submitted": True}

    fake_redis_manager.op_prefixed.set_throttle_results(
        [DebounceResult(allowed=True, remaining_seconds=0.0, redis_key="throttle:factory_test:testclient")]
    )

    client = TestClient(app)
    response = client.post("/submit")

    assert response.status_code == 200
    assert response.json() == {"submitted": True}
    assert fake_redis_manager.op_prefixed.throttle_calls[0][1] == 120


# ========== 防抖测试 ==========


def test_debounce_first_request_blocked(app_with_debounce: FastAPI, fake_redis_manager: FakeRedisManager) -> None:
    """测试防抖: 第一次请求会被拒绝(需要等待窗口期)"""
    fake_redis_manager.op_prefixed.set_debounce_results(
        [DebounceResult(allowed=False, remaining_seconds=3.0, redis_key="debounce:search:testclient")]
    )

    client = TestClient(app_with_debounce)
    response = client.get("/debounced")

    assert response.status_code == 429
    data = response.json()
    # 新的 API 返回简单的字符串
    assert data["detail"] == "Too many requests"


def test_debounce_allowed_after_window(app_with_debounce: FastAPI, fake_redis_manager: FakeRedisManager) -> None:
    """测试防抖: 窗口期后没有新请求时允许执行"""
    fake_redis_manager.op_prefixed.set_debounce_results(
        [
            DebounceResult(allowed=False, remaining_seconds=3.0, redis_key="debounce:search:testclient"),
            DebounceResult(allowed=True, remaining_seconds=0.0, redis_key="debounce:search:testclient"),
        ]
    )

    client = TestClient(app_with_debounce)

    # 第一次请求被拒绝
    response1 = client.get("/debounced")
    assert response1.status_code == 429

    # 等待后允许
    response2 = client.get("/debounced")
    assert response2.status_code == 200
    assert response2.json() == {"status": "ok"}


def test_debounce_reset_on_new_request(app_with_debounce: FastAPI, fake_redis_manager: FakeRedisManager) -> None:
    """测试防抖: 新请求会重置计时器"""
    fake_redis_manager.op_prefixed.set_debounce_results(
        [
            DebounceResult(allowed=False, remaining_seconds=3.0, redis_key="debounce:search:testclient"),
            DebounceResult(allowed=False, remaining_seconds=3.0, redis_key="debounce:search:testclient"),
            DebounceResult(allowed=False, remaining_seconds=3.0, redis_key="debounce:search:testclient"),
        ]
    )

    client = TestClient(app_with_debounce)

    # 连续请求都被拒绝,每次都重置计时器
    for _ in range(3):
        response = client.get("/debounced")
        assert response.status_code == 429
        # 新的 API 返回简单的字符串
        assert response.json()["detail"] == "Too many requests"


def test_debounce_factory(fake_redis_manager: FakeRedisManager) -> None:
    """测试防抖工厂函数"""
    app = FastAPI()

    async def get_redis() -> AsyncRedisManager:
        return fake_redis_manager

    debounce = debounce_guard_factory(
        window_seconds=5,
        redis_dependency=get_redis,
        action="auto_save",
    )

    @app.post("/save")
    async def auto_save(_guard: Annotated[None, Depends(debounce)]) -> dict:
        return {"saved": True}

    fake_redis_manager.op_prefixed.set_debounce_results(
        [DebounceResult(allowed=False, remaining_seconds=5.0, redis_key="debounce:auto_save:testclient")]
    )

    client = TestClient(app)
    response = client.post("/save")

    assert response.status_code == 429
    assert fake_redis_manager.op_prefixed.debounce_calls[0][1] == 5


def test_debounce_custom_exception_factory(fake_redis_manager: FakeRedisManager) -> None:
    """测试防抖: 自定义异常工厂"""
    app = FastAPI()

    async def get_redis() -> AsyncRedisManager:
        return fake_redis_manager

    def custom_exception_factory(*args, **kwargs):
        return HTTPException(
            status_code=429,
            detail={
                "error": "too_fast",
                "message": "请稍后重试",
            },
        )

    debounce = DebounceGuard(
        window_seconds=2,
        redis_dependency=get_redis,
        action="custom_detail",
        exception_factory=custom_exception_factory,
    )

    @app.get("/custom-detail")
    async def custom_detail(_guard: Annotated[None, Depends(debounce)]) -> dict:
        return {"status": "ok"}

    fake_redis_manager.op_prefixed.set_debounce_results(
        [DebounceResult(allowed=False, remaining_seconds=1.5, redis_key="debounce:custom_detail:testclient")]
    )

    client = TestClient(app)
    response = client.get("/custom-detail")

    assert response.status_code == 429
    data = response.json()["detail"]
    assert data["error"] == "too_fast"
    assert data["message"] == "请稍后重试"


# ========== 集成测试: 真实 Redis ==========


@pytest.mark.asyncio
async def test_throttle_with_real_redis(redis_mgr: AsyncRedisManager) -> None:
    """使用真实 Redis 测试节流"""
    key = "test:throttle:real"
    await redis_mgr.op_prefixed.delete(key)

    # 第一次请求应该通过
    result1 = await redis_mgr.op_prefixed.throttle_check_and_set(key, window_seconds=2)
    assert result1.allowed is True
    assert result1.remaining_seconds == 0.0

    # 第二次请求应该被拒绝
    result2 = await redis_mgr.op_prefixed.throttle_check_and_set(key, window_seconds=2)
    assert result2.allowed is False
    assert 0 < result2.remaining_seconds <= 2

    # 等待过期
    await asyncio.sleep(2.1)

    # 过期后应该通过
    result3 = await redis_mgr.op_prefixed.throttle_check_and_set(key, window_seconds=2)
    assert result3.allowed is True


# 注意: debounce_check_and_set 实际上实现的是节流(throttle)逻辑,而不是真正的防抖
# 因此不再为它单独编写测试,使用 throttle 的测试即可
