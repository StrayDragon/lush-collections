"""测试互斥锁守卫的边界情况和异常处理"""  # noqa: INP001

import pytest
from fastapi import Depends, FastAPI, status
from fastapi.testclient import TestClient
from starlette.requests import Request

from lush_redisx import AsyncRedisManager
from lush_redisx.integrations.fastapi.depends.mutex import (
    MutexGuard,
    UserIDMutexKeyBuilder,
    _maybe_await_str,
    mutex_guard_factory,
)


class FakeRedisManager:
    def __init__(self, set_result: bool = True, *, delete_exception: Exception | None = None) -> None:
        self.deleted_keys = []
        self.locks = {}
        self.set_result = set_result
        self.delete_exception = delete_exception

    @property
    def op_prefixed(self) -> "FakeRedisManager":
        return self

    async def set(self, key: str, value: str, *, expire: int, nx: bool) -> bool:
        if nx and key in self.locks:
            return False
        self.locks[key] = True
        return self.set_result

    async def delete(self, key: str) -> int:
        if self.delete_exception is not None:
            raise self.delete_exception
        self.deleted_keys.append(key)
        if key in self.locks:
            del self.locks[key]
            return 1
        return 0


class TestMaybeAwaitStrMutex:
    """测试 mutex 模块的 _maybe_await_str 函数"""

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


class TestMutexGuardValidation:
    """测试 MutexGuard 参数验证"""

    def test_timeout_seconds_must_be_positive(self) -> None:
        """测试 timeout_seconds 必须大于 0"""

        def redis_dep() -> AsyncRedisManager:
            return FakeRedisManager()  # type: ignore[reportReturnType]

        with pytest.raises(ValueError, match="timeout_seconds 必须大于 0"):
            MutexGuard(
                timeout_seconds=0,
                redis_dependency=redis_dep,
                action="test",
            )

    def test_timeout_seconds_negative_raises(self) -> None:
        """测试负数 timeout_seconds 抛出异常"""

        def redis_dep() -> AsyncRedisManager:
            return FakeRedisManager()  # type: ignore[reportReturnType]

        with pytest.raises(ValueError):
            MutexGuard(
                timeout_seconds=-1,
                redis_dependency=redis_dep,
                action="test",
            )


class TestUserIDMutexKeyBuilder:
    """测试 UserIDMutexKeyBuilder"""

    @pytest.mark.asyncio
    async def test_build_key_with_user_id(self) -> None:
        """测试有用户 ID 时生成正确的键"""
        builder = UserIDMutexKeyBuilder("test_action")
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/test",
            "client": ("127.0.0.1", 1234),
            "headers": [],
        }
        request = Request(scope, lambda: None)

        key = await builder.build_key(request, context=12345)
        assert key == "mutex:test_action:user:12345"

    @pytest.mark.asyncio
    async def test_build_key_without_user_id_uses_ip(self) -> None:
        """测试没有用户 ID 时回退到 IP"""
        builder = UserIDMutexKeyBuilder("test_action")
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/test",
            "client": ("203.0.113.10", 1234),
            "headers": [],
        }
        request = Request(scope, lambda: None)

        key = await builder.build_key(request, context=None)
        assert key == "mutex:test_action:ip:203.0.113.10"

    @pytest.mark.asyncio
    async def test_build_key_without_client(self) -> None:
        """测试没有客户端信息时使用 unknown"""
        builder = UserIDMutexKeyBuilder("test_action")
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/test",
            "client": None,
            "headers": [],
        }
        request = Request(scope, lambda: None)

        key = await builder.build_key(request, context=None)
        assert key == "mutex:test_action:ip:unknown"


class TestMutexGuardWithCustomKeyBuilder:
    """测试带自定义 key_builder 的 MutexGuard"""

    def test_custom_key_builder_class(self) -> None:
        """测试使用自定义键构建器类"""
        from lush_redisx.integrations.fastapi.depends.mutex import MutexKeyBuilder

        fake_redis = FakeRedisManager()

        class CustomKeyBuilder(MutexKeyBuilder):
            async def build_key(self, request, context) -> str:
                return f"custom:{context}:{request.method}"

        guard = MutexGuard(
            timeout_seconds=30,
            redis_dependency=lambda: fake_redis,
            action="test",
            key_builder=CustomKeyBuilder(),
        )

        from lush_redisx.integrations.fastapi.middleware import MutexReleaseMiddleware

        app = FastAPI()
        app.add_middleware(MutexReleaseMiddleware)

        @app.post("/test", dependencies=[Depends(guard)])
        async def test_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app)
        response = client.post("/test")

        assert response.status_code == 200

    def test_custom_key_builder_callable(self) -> None:
        """测试使用自定义键构建器函数"""
        fake_redis = FakeRedisManager()

        def custom_key_builder(request, context) -> str:
            return f"callable:{context}:{request.method}"

        guard = MutexGuard(
            timeout_seconds=30,
            redis_dependency=lambda: fake_redis,
            action="test",
            key_builder=custom_key_builder,
        )

        app = FastAPI()

        @app.post("/test", dependencies=[Depends(guard)])
        async def test_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app)
        response = client.post("/test")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_custom_key_builder_async_callable(self) -> None:
        """测试使用异步自定义键构建器函数"""
        fake_redis = FakeRedisManager()

        async def async_key_builder(request, context) -> str:
            return f"async:{context}"

        guard = MutexGuard(
            timeout_seconds=30,
            redis_dependency=lambda: fake_redis,
            action="test",
            key_builder=async_key_builder,
        )

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/test",
            "client": ("127.0.0.1", 1234),
            "headers": [],
        }
        request = Request(scope, lambda: None)

        await guard(request, fake_redis, "context-value")


class TestMutexGuardWithContextDependency:
    """测试带 context_dependency 的 MutexGuard"""

    def test_with_context_dependency(self) -> None:
        """测试带 context_dependency 的互斥守卫"""
        fake_redis = FakeRedisManager()

        guard = MutexGuard(
            timeout_seconds=30,
            redis_dependency=lambda: fake_redis,
            action="test",
            context_dependency=lambda: 12345,
            context_annotation=int,
        )

        app = FastAPI()

        @app.post("/test", dependencies=[Depends(guard)])
        async def test_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app)
        response = client.post("/test")

        assert response.status_code == 200


class TestMutexGuardWithCustomException:
    """测试带自定义异常的 MutexGuard"""

    def test_custom_exception_factory(self) -> None:
        """测试自定义异常工厂"""
        fake_redis = FakeRedisManager(set_result=False)

        class CustomConflictError(Exception):
            pass

        def custom_exception_factory(request: Request, redis_key: str, timeout: int, context):
            return CustomConflictError(f"Operation in progress: {redis_key}")

        guard = MutexGuard(
            timeout_seconds=30,
            redis_dependency=lambda: fake_redis,
            action="test",
            exception_factory=custom_exception_factory,
        )

        app = FastAPI()

        @app.post("/test", dependencies=[Depends(guard)])
        async def test_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)

        response = client.post("/test")
        assert response.status_code == 500


class TestMutexGuardDefaultException:
    """测试互斥守卫默认异常行为"""

    def test_default_exception_returns_409(self) -> None:
        """测试默认异常返回 409 Conflict"""
        fake_redis = FakeRedisManager(set_result=False)

        guard = MutexGuard(
            timeout_seconds=30,
            redis_dependency=lambda: fake_redis,
            action="test",
        )

        app = FastAPI()

        @app.post("/test", dependencies=[Depends(guard)])
        async def test_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app)

        response = client.post("/test")
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["detail"] == "Operation in progress"


class TestMutexGuardFactory:
    """测试 mutex_guard_factory 工厂函数"""

    def test_factory_creates_valid_guard(self) -> None:
        """测试工厂函数创建有效的守卫"""
        fake_redis = FakeRedisManager()

        guard = mutex_guard_factory(
            timeout_seconds=60,
            redis_dependency=lambda: fake_redis,
            key_builder=None,
            action="factory_test",
            context_dependency=lambda: "user",
            context_annotation=str,
            state_key="_custom_locks",
        )

        assert guard._timeout_seconds == 60
        assert guard._action == "factory_test"
        assert guard._state_key == "_custom_locks"

    def test_factory_with_custom_action(self) -> None:
        """测试工厂函数使用自定义 action"""
        fake_redis = FakeRedisManager()

        guard = mutex_guard_factory(
            timeout_seconds=30,
            redis_dependency=lambda: fake_redis,
            action="custom_action_name",
        )

        # 验证 action 被正确使用
        assert guard._action == "custom_action_name"


class TestMutexGuardEdgeCases:
    """测试互斥守卫边界情况"""

    def test_lock_acquisition_first_time(self) -> None:
        """测试首次获取锁"""
        fake_redis = FakeRedisManager(set_result=True)

        guard = MutexGuard(
            timeout_seconds=30,
            redis_dependency=lambda: fake_redis,
            action="test",
        )

        from lush_redisx.integrations.fastapi.middleware import MutexReleaseMiddleware

        app = FastAPI()
        app.add_middleware(MutexReleaseMiddleware)

        @app.post("/test", dependencies=[Depends(guard)])
        async def test_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app)
        response = client.post("/test")

        assert response.status_code == 200
        assert len(fake_redis.locks) == 0  # 请求结束后锁被释放

    def test_lock_block_second_request(self) -> None:
        """测试锁阻止第二次请求"""
        fake_redis = FakeRedisManager()

        # 第一次请求后锁仍然存在
        fake_redis.locks["mutex:test:ip:testclient"] = True

        guard = MutexGuard(
            timeout_seconds=30,
            redis_dependency=lambda: fake_redis,
            action="test",
        )

        app = FastAPI()

        @app.post("/test", dependencies=[Depends(guard)])
        async def test_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app)
        response = client.post("/test")

        assert response.status_code == status.HTTP_409_CONFLICT


class TestMutexAutoReleaseMiddlewareException:
    """测试中间件异常处理"""

    def test_middleware_handles_delete_exception(self) -> None:
        """测试中间件处理删除锁时的异常"""
        fake_redis = FakeRedisManager(delete_exception=Exception("Delete failed"))

        from lush_redisx.integrations.fastapi.depends.mutex import create_mutex_auto_release_middleware

        custom_middleware = create_mutex_auto_release_middleware(lambda req: getattr(req.state, "_mutex_locks", []))

        app = FastAPI()
        app.add_middleware(custom_middleware)

        async def get_redis() -> AsyncRedisManager:
            return fake_redis  # type: ignore[reportReturnType]

        guard = MutexGuard(
            timeout_seconds=30,
            redis_dependency=get_redis,
            action="test",
        )

        @app.post("/test", dependencies=[Depends(guard)])
        async def test_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app)
        response = client.post("/test")

        # 即使删除失败,请求也应该成功
        assert response.status_code == 200


class TestMutexKeyBuilderWithEmptyContext:
    """测试空上下文场景"""

    @pytest.mark.asyncio
    async def test_build_key_with_empty_string_context(self) -> None:
        """测试空字符串上下文"""
        builder = UserIDMutexKeyBuilder("test")
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/test",
            "client": ("127.0.0.1", 1234),
            "headers": [],
        }
        request = Request(scope, lambda: None)

        # 空字符串应该被使用,不会回退到 IP
        key = await builder.build_key(request, context="")
        assert key == "mutex:test:user:"


class TestMutexGuardSignature:
    """测试 MutexGuard 签名"""

    def test_signature_without_context_dependency(self) -> None:
        """测试没有 context_dependency 时的签名"""
        guard = MutexGuard(
            timeout_seconds=30,
            redis_dependency=lambda: None,  # type: ignore[reportReturnType]
            action="test",
        )

        # 签名应该只包含 request 和 redis_mgr
        params = list(guard.__signature__.parameters.keys())
        assert "request" in params
        assert "redis_mgr" in params
        assert "context" not in params

    def test_signature_with_context_dependency(self) -> None:
        """测试有 context_dependency 时的签名"""
        guard = MutexGuard(
            timeout_seconds=30,
            redis_dependency=lambda: None,  # type: ignore[reportReturnType]
            action="test",
            context_dependency=lambda: "user",
            context_annotation=str,
        )

        params = list(guard.__signature__.parameters.keys())
        assert "request" in params
        assert "redis_mgr" in params
        assert "context" in params
