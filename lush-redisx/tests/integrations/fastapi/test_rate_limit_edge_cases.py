"""测试速率限制守卫的边界情况和异常处理"""  # noqa: INP001

import pytest
from fastapi import Depends, FastAPI, status
from fastapi.testclient import TestClient
from starlette.requests import Request

from lush_redisx import AsyncRedisManager, DebounceResult
from lush_redisx.integrations.fastapi.depends.rate_limit import (
    ClientIPRateLimitKeyBuilder,
    DebounceGuard,
    RateLimitKeyBuilder,
    ThrottleGuard,
    _maybe_await_str,
    debounce_guard_factory,
    throttle_guard_factory,
)


class FakeRedisManager:
    def __init__(self, throttle_result: DebounceResult | None = None) -> None:
        self.throttle_calls = []
        self.debounce_calls = []
        self.throttle_result = throttle_result or DebounceResult(allowed=True, remaining_seconds=0.0, redis_key="test")

    @property
    def op_prefixed(self) -> "FakeRedisManager":
        return self

    async def throttle_check_and_set(self, key: str, *, window_seconds: int) -> DebounceResult:
        self.throttle_calls.append((key, window_seconds))
        return self.throttle_result

    async def debounce_check_and_set(self, key: str, *, window_seconds: int) -> DebounceResult:
        self.debounce_calls.append((key, window_seconds))
        return self.throttle_result


class TestMaybeAwaitStrRateLimit:
    """测试 rate_limit 模块的 _maybe_await_str 函数"""

    @pytest.mark.asyncio
    async def test_maybe_await_str_with_string(self) -> None:
        """测试传入字符串时直接返回"""
        result = await _maybe_await_str("already_a_string")
        assert result == "already_a_string"

    @pytest.mark.asyncio
    async def test_maybe_await_str_with_awaitable(self) -> None:
        """测试传入 Awaitable 时等待结果"""

        async def async_str() -> str:
            return "async_string"

        result = await _maybe_await_str(async_str())
        assert result == "async_string"


class TestRateLimitValidation:
    """测试速率限制守卫参数验证"""

    def test_throttle_window_seconds_must_be_positive(self) -> None:
        """测试 throttle window_seconds 必须大于 0"""

        def redis_dep() -> AsyncRedisManager:
            return FakeRedisManager()  # type: ignore[reportReturnType]

        with pytest.raises(ValueError, match="window_seconds 必须大于 0"):
            ThrottleGuard(
                window_seconds=0,
                redis_dependency=redis_dep,
                action="test",
            )

    def test_debounce_window_seconds_must_be_positive(self) -> None:
        """测试 debounce window_seconds 必须大于 0"""

        def redis_dep() -> AsyncRedisManager:
            return FakeRedisManager()  # type: ignore[reportReturnType]

        with pytest.raises(ValueError, match="window_seconds 必须大于 0"):
            DebounceGuard(
                window_seconds=-1,
                redis_dependency=redis_dep,
                action="test",
            )


class TestClientIPRateLimitKeyBuilder:
    """测试 ClientIPRateLimitKeyBuilder"""

    @pytest.mark.asyncio
    async def test_build_key_with_client_ip(self) -> None:
        """测试使用客户端 IP 生成键"""
        builder = ClientIPRateLimitKeyBuilder("test_action", "throttle")
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/test",
            "client": ("203.0.113.10", 1234),
            "headers": [],
        }
        request = Request(scope, lambda: None)

        key = await builder.build_key(request, context=None)
        assert key == "throttle:test_action:203.0.113.10"

    @pytest.mark.asyncio
    async def test_build_key_with_forwarded_for(self) -> None:
        """测试使用 X-Forwarded-For 头生成键"""
        builder = ClientIPRateLimitKeyBuilder("test_action", "throttle")
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/test",
            "client": ("203.0.113.1", 1234),
            "headers": [(b"x-forwarded-for", b"198.51.100.23, 203.0.113.1")],
        }
        request = Request(scope, lambda: None)

        key = await builder.build_key(request, context=None)
        assert key == "throttle:test_action:198.51.100.23"

    @pytest.mark.asyncio
    async def test_build_key_without_client(self) -> None:
        """测试没有客户端时使用 unknown"""
        builder = ClientIPRateLimitKeyBuilder("test_action", "throttle")
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/test",
            "client": None,
            "headers": [],
        }
        request = Request(scope, lambda: None)

        key = await builder.build_key(request, context=None)
        assert key == "throttle:test_action:unknown"

    @pytest.mark.asyncio
    async def test_build_key_for_debounce(self) -> None:
        """测试防抖键格式"""
        builder = ClientIPRateLimitKeyBuilder("search", "debounce")
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/search",
            "client": ("127.0.0.1", 1234),
            "headers": [],
        }
        request = Request(scope, lambda: None)

        key = await builder.build_key(request, context=None)
        assert key == "debounce:search:127.0.0.1"


class TestThrottleGuardWithContextDependency:
    """测试带 context_dependency 的 ThrottleGuard"""

    def test_throttle_with_context_dependency(self) -> None:
        """测试带 context_dependency 的节流守卫"""
        fake_redis = FakeRedisManager()

        guard = ThrottleGuard(
            window_seconds=60,
            redis_dependency=lambda: fake_redis,
            action="test",
            context_dependency=lambda: "user-123",
            context_annotation=str,
        )

        app = FastAPI()

        @app.get("/test", dependencies=[Depends(guard)])
        async def test_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200


class TestDebounceGuardWithContextDependency:
    """测试带 context_dependency 的 DebounceGuard"""

    def test_debounce_with_context_dependency(self) -> None:
        """测试带 context_dependency 的防抖守卫"""
        fake_redis = FakeRedisManager()

        guard = DebounceGuard(
            window_seconds=3,
            redis_dependency=lambda: fake_redis,
            action="search",
            context_dependency=lambda: "user-123",
            context_annotation=str,
        )

        app = FastAPI()

        @app.get("/search", dependencies=[Depends(guard)])
        async def search_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/search")

        assert response.status_code == 200


class TestThrottleGuardWithCustomKeyBuilder:
    """测试带自定义 key_builder 的 ThrottleGuard"""

    def test_throttle_custom_key_builder_callable(self) -> None:
        """测试使用自定义键构建器函数的节流守卫"""
        fake_redis = FakeRedisManager()

        def custom_key_builder(request, context) -> str:
            return f"custom:{context}:{request.method}"

        guard = ThrottleGuard(
            window_seconds=60,
            redis_dependency=lambda: fake_redis,
            action="test",
            key_builder=custom_key_builder,
        )

        app = FastAPI()

        @app.get("/test", dependencies=[Depends(guard)])
        async def test_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200
        assert len(fake_redis.throttle_calls) == 1

    @pytest.mark.asyncio
    async def test_throttle_custom_key_builder_async_callable(self) -> None:
        """测试使用异步自定义键构建器函数的节流守卫"""
        fake_redis = FakeRedisManager()

        async def async_key_builder(request, context) -> str:
            return f"async:{context}"

        guard = ThrottleGuard(
            window_seconds=60,
            redis_dependency=lambda: fake_redis,
            action="test",
            key_builder=async_key_builder,
        )

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "client": ("127.0.0.1", 1234),
            "headers": [],
        }
        request = Request(scope, lambda: None)

        await guard(request, fake_redis, "context-value")


class TestDebounceGuardWithCustomKeyBuilder:
    """测试带自定义 key_builder 的 DebounceGuard"""

    def test_debounce_custom_key_builder_class(self) -> None:
        """测试使用自定义键构建器类的防抖守卫"""

        class CustomKeyBuilder(RateLimitKeyBuilder):
            async def build_key(self, request, context) -> str:
                return f"custom:{context}:{request.method}"

        fake_redis = FakeRedisManager()

        guard = DebounceGuard(
            window_seconds=3,
            redis_dependency=lambda: fake_redis,
            action="test",
            key_builder=CustomKeyBuilder(),
        )

        app = FastAPI()

        @app.get("/test", dependencies=[Depends(guard)])
        async def test_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200

    def test_debounce_custom_key_builder_callable(self) -> None:
        """测试使用自定义键构建器函数的防抖守卫"""
        fake_redis = FakeRedisManager()

        def custom_key_builder(request, context) -> str:
            return f"callable:{context}:{request.method}"

        guard = DebounceGuard(
            window_seconds=3,
            redis_dependency=lambda: fake_redis,
            action="test",
            key_builder=custom_key_builder,
        )

        app = FastAPI()

        @app.get("/test", dependencies=[Depends(guard)])
        async def test_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200


class TestThrottleGuardWithCustomException:
    """测试带自定义异常的 ThrottleGuard"""

    def test_throttle_custom_exception_factory(self) -> None:
        """测试自定义异常工厂"""
        fake_redis = FakeRedisManager(
            throttle_result=DebounceResult(allowed=False, remaining_seconds=30.0, redis_key="throttle:test:testclient")
        )

        class CustomRateLimitError(Exception):
            pass

        def custom_exception_factory(request: Request, redis_key: str, remaining: float, context):
            return CustomRateLimitError(f"Rate limited: {remaining}s remaining")

        guard = ThrottleGuard(
            window_seconds=60,
            redis_dependency=lambda: fake_redis,
            action="test",
            exception_factory=custom_exception_factory,
        )

        app = FastAPI()

        @app.get("/test", dependencies=[Depends(guard)])
        async def test_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/test")
        assert response.status_code == 500


class TestDebounceGuardWithCustomException:
    """测试带自定义异常的 DebounceGuard"""

    def test_debounce_custom_exception_factory(self) -> None:
        """测试自定义异常工厂"""
        fake_redis = FakeRedisManager(
            throttle_result=DebounceResult(allowed=False, remaining_seconds=5.0, redis_key="debounce:test:testclient")
        )

        class CustomDebounceError(Exception):
            pass

        def custom_exception_factory(request: Request, redis_key: str, remaining: float, context):
            return CustomDebounceError(f"Debounced: {remaining}s remaining")

        guard = DebounceGuard(
            window_seconds=3,
            redis_dependency=lambda: fake_redis,
            action="test",
            exception_factory=custom_exception_factory,
        )

        app = FastAPI()

        @app.get("/test", dependencies=[Depends(guard)])
        async def test_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/test")
        assert response.status_code == 500


class TestThrottleGuardDefaultException:
    """测试 ThrottleGuard 默认异常"""

    def test_throttle_default_exception(self) -> None:
        """测试默认异常返回 429"""
        fake_redis = FakeRedisManager(
            throttle_result=DebounceResult(allowed=False, remaining_seconds=30.0, redis_key="throttle:test:testclient")
        )

        guard = ThrottleGuard(
            window_seconds=60,
            redis_dependency=lambda: fake_redis,
            action="test",
        )

        app = FastAPI()

        @app.get("/test", dependencies=[Depends(guard)])
        async def test_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app)

        response = client.get("/test")
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert response.json()["detail"] == "Too many requests"


class TestDebounceGuardDefaultException:
    """测试 DebounceGuard 默认异常"""

    def test_debounce_default_exception(self) -> None:
        """测试默认异常返回 429"""
        fake_redis = FakeRedisManager(
            throttle_result=DebounceResult(allowed=False, remaining_seconds=5.0, redis_key="debounce:test:testclient")
        )

        guard = DebounceGuard(
            window_seconds=3,
            redis_dependency=lambda: fake_redis,
            action="test",
        )

        app = FastAPI()

        @app.get("/test", dependencies=[Depends(guard)])
        async def test_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app)

        response = client.get("/test")
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


class TestThrottleGuardFactory:
    """测试 throttle_guard_factory 工厂函数"""

    def test_factory_creates_valid_guard(self) -> None:
        """测试工厂函数创建有效的守卫"""
        fake_redis = FakeRedisManager()

        guard = throttle_guard_factory(
            window_seconds=120,
            redis_dependency=lambda: fake_redis,
            action="factory_test",
        )

        assert guard._window_seconds == 120

    def test_factory_with_custom_key_builder(self) -> None:
        """测试工厂函数使用自定义 key_builder"""
        fake_redis = FakeRedisManager()

        def custom_key_builder(request, context) -> str:
            return f"custom:{context}"

        guard = throttle_guard_factory(
            window_seconds=60,
            redis_dependency=lambda: fake_redis,
            action="test",
            key_builder=custom_key_builder,
        )

        assert callable(guard._key_builder)


class TestDebounceGuardFactory:
    """测试 debounce_guard_factory 工厂函数"""

    def test_factory_creates_valid_guard(self) -> None:
        """测试工厂函数创建有效的守卫"""
        fake_redis = FakeRedisManager()

        guard = debounce_guard_factory(
            window_seconds=5,
            redis_dependency=lambda: fake_redis,
            action="factory_test",
        )

        assert guard._window_seconds == 5

    def test_factory_with_custom_key_builder(self) -> None:
        """测试工厂函数使用自定义 key_builder"""
        fake_redis = FakeRedisManager()

        def custom_key_builder(request, context) -> str:
            return f"custom:{context}"

        guard = debounce_guard_factory(
            window_seconds=3,
            redis_dependency=lambda: fake_redis,
            action="test",
            key_builder=custom_key_builder,
        )

        assert callable(guard._key_builder)


class TestRateLimitKeyBuilderAbstract:
    """测试 RateLimitKeyBuilder 抽象基类"""

    def test_abstract_build_key_raises(self) -> None:
        """测试抽象类的 build_key 方法必须实现"""

        class IncompleteKeyBuilder(RateLimitKeyBuilder):
            pass

        with pytest.raises(TypeError):
            IncompleteKeyBuilder()  # type: ignore[reportAbstractUsage]


class TestThrottleBuildKeyMethod:
    """测试 ThrottleGuard._build_key 方法"""

    @pytest.mark.asyncio
    async def test_build_key_with_class_builder(self) -> None:
        """测试使用类级别的键构建器"""
        fake_redis = FakeRedisManager()
        builder = ClientIPRateLimitKeyBuilder("action", "throttle")

        guard = ThrottleGuard(
            window_seconds=60,
            redis_dependency=lambda: fake_redis,
            key_builder=builder,
            action="test",
        )

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "client": ("127.0.0.1", 1234),
            "headers": [],
        }
        request = Request(scope, lambda: None)

        key = await guard._build_key(request, None)
        assert key == "throttle:action:127.0.0.1"


class TestDebounceBuildKeyMethod:
    """测试 DebounceGuard._build_key 方法"""

    @pytest.mark.asyncio
    async def test_build_key_with_class_builder(self) -> None:
        """测试使用类级别的键构建器"""
        fake_redis = FakeRedisManager()
        builder = ClientIPRateLimitKeyBuilder("search", "debounce")

        guard = DebounceGuard(
            window_seconds=3,
            redis_dependency=lambda: fake_redis,
            key_builder=builder,
            action="test",
        )

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/search",
            "client": ("127.0.0.1", 1234),
            "headers": [],
        }
        request = Request(scope, lambda: None)

        key = await guard._build_key(request, None)
        assert key == "debounce:search:127.0.0.1"


class TestRateLimitSignature:
    """测试速率限制守卫签名"""

    def test_throttle_signature_without_context(self) -> None:
        """测试没有 context_dependency 时的 throttle 签名"""
        guard = ThrottleGuard(
            window_seconds=60,
            redis_dependency=lambda: None,  # type: ignore[reportReturnType]
            action="test",
        )

        params = list(guard.__signature__.parameters.keys())
        assert "request" in params
        assert "redis_mgr" in params
        assert "context" not in params

    def test_debounce_signature_without_context(self) -> None:
        """测试没有 context_dependency 时的 debounce 签名"""
        guard = DebounceGuard(
            window_seconds=3,
            redis_dependency=lambda: None,  # type: ignore[reportReturnType]
            action="test",
        )

        params = list(guard.__signature__.parameters.keys())
        assert "request" in params
        assert "redis_mgr" in params
        assert "context" not in params

    def test_throttle_signature_with_context(self) -> None:
        """测试有 context_dependency 时的 throttle 签名"""
        guard = ThrottleGuard(
            window_seconds=60,
            redis_dependency=lambda: None,  # type: ignore[reportReturnType]
            action="test",
            context_dependency=lambda: "user",
            context_annotation=str,
        )

        params = list(guard.__signature__.parameters.keys())
        assert "request" in params
        assert "redis_mgr" in params
        assert "context" in params
