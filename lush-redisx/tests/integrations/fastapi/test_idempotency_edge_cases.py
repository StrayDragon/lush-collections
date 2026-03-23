"""测试幂等守卫的边界情况和异常处理"""  # noqa: INP001

import pytest
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from starlette.requests import Request

from lush_redisx import AsyncRedisManager
from lush_redisx.integrations.fastapi.depends.idempotency import IdempotencyGuard, _maybe_await_str, idempotency_guard_factory


class FakePrefixedOp:
    def __init__(self, set_result: bool = True) -> None:
        self.set_calls = []
        self.set_result = set_result

    async def set(self, key: str, value: str, *, expire: int, nx: bool) -> bool:
        self.set_calls.append((key, value, expire, nx))
        return self.set_result


class FakeRedisManager:
    def __init__(self, set_result: bool = True) -> None:
        self.op_prefixed = FakePrefixedOp(set_result)


class TestMaybeAwaitStr:
    """测试 _maybe_await_str 函数"""

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


class TestIdempotencyGuardValidation:
    """测试 IdempotencyGuard 参数验证"""

    def test_ttl_seconds_must_be_positive(self) -> None:
        """测试 ttl_seconds 必须大于 0"""

        def redis_dep() -> AsyncRedisManager:
            return FakeRedisManager()  # type: ignore[reportReturnType]

        with pytest.raises(ValueError, match="ttl_seconds 必须大于 0"):
            IdempotencyGuard(
                redis_dependency=redis_dep,
                ttl_seconds=0,
            )

    def test_ttl_seconds_negative_raises(self) -> None:
        """测试负数 ttl_seconds 抛出异常"""

        def redis_dep() -> AsyncRedisManager:
            return FakeRedisManager()  # type: ignore[reportReturnType]

        with pytest.raises(ValueError):
            IdempotencyGuard(
                redis_dependency=redis_dep,
                ttl_seconds=-1,
            )


class TestIdempotencyGuardWithContext:
    """测试带 context_dependency 的幂等守卫"""

    def test_idempotency_with_context_dependency(self) -> None:
        """测试带 context_dependency 的幂等守卫"""
        fake_manager = FakeRedisManager(set_result=True)

        guard = idempotency_guard_factory(
            redis_dependency=lambda: fake_manager,
            ttl_seconds=30,
            context_dependency=lambda: "user-123",
            context_annotation=str,
        )

        app = FastAPI()

        @app.post("/test", dependencies=[Depends(guard)])
        async def test_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app)
        response = client.post("/test", json={"data": "test"})

        assert response.status_code == 200


class TestIdempotencyWriteMethodsOnly:
    """测试 write_methods_only 参数"""

    def test_read_method_bypasses_idempotency(self) -> None:
        """测试 GET 等读取方法应该直接通过"""
        fake_manager = FakeRedisManager(set_result=True)

        guard = idempotency_guard_factory(
            redis_dependency=lambda: fake_manager,
            ttl_seconds=30,
            write_methods_only=True,  # 默认值
        )

        app = FastAPI()

        @app.get("/test", dependencies=[Depends(guard)])
        async def test_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        # GET 请求应该直接通过,不设置任何 Redis 键
        assert response.status_code == 200
        assert len(fake_manager.op_prefixed.set_calls) == 0


class TestIdempotencyFallbackKey:
    """测试没有幂等 key header 时的回退逻辑"""

    def test_fallback_key_material(self) -> None:
        """测试回退键材料生成"""
        fake_manager = FakeRedisManager(set_result=True)  # 第一次调用返回 True

        def custom_user_id(_request: Request, _context):
            return "custom-user"

        guard = idempotency_guard_factory(
            redis_dependency=lambda: fake_manager,
            ttl_seconds=30,
            user_identifier_getter=custom_user_id,
        )

        app = FastAPI()

        @app.post("/test", dependencies=[Depends(guard)])
        async def test_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app)

        # 第一次请求应该成功
        response1 = client.post("/test", json={"data": "test"})
        assert response1.status_code == 200

        # 验证 Redis 调用
        assert len(fake_manager.op_prefixed.set_calls) == 1


class TestIdempotencyUserIdentifierAwaitable:
    """测试 user_identifier_getter 返回 Awaitable 的情况"""

    @pytest.mark.asyncio
    async def test_async_user_identifier_getter(self) -> None:
        """测试异步 user_identifier_getter"""
        fake_manager = FakeRedisManager(set_result=True)

        async def async_user_id(_request: Request, _context) -> str:
            return "async-user"

        guard = IdempotencyGuard(
            redis_dependency=lambda: fake_manager,
            ttl_seconds=30,
            user_identifier_getter=async_user_id,
        )

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "method": "POST",
            "path": "/test",
            "headers": [],
            "query_string": b"",
            "client": ("testclient", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
        }

        async def receive() -> dict:
            return {"type": "http.request", "body": b'{"test": "data"}', "more_body": False}

        request = Request(scope, receive)

        # 应该成功,不抛出异常
        await guard(request, fake_manager, None)


class TestIdempotencyCustomException:
    """测试自定义异常工厂"""

    def test_custom_exception_factory(self) -> None:
        """测试自定义异常工厂"""
        fake_manager = FakeRedisManager(set_result=False)

        class CustomRateLimitError(Exception):
            pass

        def custom_exception_factory(request: Request, redis_key: str, ttl: int, context):
            return CustomRateLimitError(f"Rate limited: {redis_key}")

        guard = idempotency_guard_factory(
            redis_dependency=lambda: fake_manager,
            ttl_seconds=30,
            exception_factory=custom_exception_factory,
        )

        app = FastAPI()

        @app.post("/test", dependencies=[Depends(guard)])
        async def test_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)

        response = client.post("/test", json={"data": "test"})

        # 应该返回自定义异常的状态码(500 因为未处理的异常)
        assert response.status_code == 500


class TestIdempotencyFactoryFunction:
    """测试工厂函数"""

    def test_factory_creates_valid_guard(self) -> None:
        """测试工厂函数创建有效的守卫"""
        fake_manager = FakeRedisManager(set_result=True)

        guard = idempotency_guard_factory(
            redis_dependency=lambda: fake_manager,
            ttl_seconds=60,
            write_methods_only=False,
            header_candidates=["X-Custom-Idempotency-Key"],
            cache_prefix="custom:idemp",
        )

        assert guard._ttl_seconds == 60
        assert guard._write_methods_only is False
        assert "X-Custom-Idempotency-Key" in guard._header_candidates
        assert guard._cache_prefix == "custom:idemp"


class TestIdempotencyDefaultExceptionFactory:
    """测试默认异常工厂"""

    def test_default_exception_factory_returns_httpexception(self) -> None:
        """测试默认异常工厂返回正确的 HTTPException"""
        from lush_redisx.integrations.fastapi.depends.idempotency import IdempotencyGuard

        # 通过反射调用静态方法
        result = IdempotencyGuard._default_exception_factory(
            None,  # type: ignore[reportArgumentType]
            "test:key",
            30,
            None,
        )

        assert isinstance(result, HTTPException)
        assert result.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert result.detail["message"] == "重复提交"
        assert result.detail["redis_key"] == "test:key"
        assert result.detail["ttl_seconds"] == 30


class TestIdempotencyDefaultBodyBuilder:
    """测试默认 body builder"""

    @pytest.mark.asyncio
    async def test_default_body_builder(self) -> None:
        """测试默认 body builder 正确解析请求体"""
        from lush_redisx.integrations.fastapi.depends.idempotency import IdempotencyGuard

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "method": "POST",
            "path": "/test",
            "headers": [],
            "query_string": b"",
            "client": ("testclient", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
        }

        body_content = b'{"key": "value"}'

        async def receive() -> dict:
            return {"type": "http.request", "body": body_content, "more_body": False}

        request = Request(scope, receive)

        result = await IdempotencyGuard._default_body_builder(request, None)
        assert result == '{"key": "value"}'


class TestIdempotencyDefaultUserIdentifier:
    """测试默认用户标识符"""

    def test_default_user_identifier_anonymous(self) -> None:
        """测试默认用户标识符对 anonymous 上下文返回 'anonymous'"""
        from lush_redisx.integrations.fastapi.depends.idempotency import IdempotencyGuard

        result = IdempotencyGuard._default_user_identifier(None, None)  # type: ignore[reportArgumentType]
        assert result == "anonymous"

    def test_default_user_identifier_with_context(self) -> None:
        """测试默认用户标识符对非空上下文返回 str(context)"""
        from lush_redisx.integrations.fastapi.depends.idempotency import IdempotencyGuard

        result = IdempotencyGuard._default_user_identifier(None, "user-123")  # type: ignore[reportArgumentType]
        assert result == "user-123"


class TestIdempotencyHeaderValueUsage:
    """测试使用 header 中幂等 key 的场景 (行 99)"""

    def test_idempotency_with_header_value(self) -> None:
        """测试使用 header 中的幂等 key (行 99)"""
        fake_manager = FakeRedisManager(set_result=True)

        guard = idempotency_guard_factory(
            redis_dependency=lambda: fake_manager,
            ttl_seconds=30,
            header_candidates=["X-Idempotency-Key"],
        )

        app = FastAPI()

        @app.post("/test", dependencies=[Depends(guard)])
        async def test_endpoint() -> dict:
            return {"status": "ok"}

        client = TestClient(app)

        # 使用自定义 header
        response = client.post("/test", json={"data": "test"}, headers={"X-Idempotency-Key": "my-custom-key"})
        assert response.status_code == 200

        # 验证使用了自定义 header 值
        assert len(fake_manager.op_prefixed.set_calls) == 1
        key, value, expire, nx = fake_manager.op_prefixed.set_calls[0]
        assert "my-custom-key" in key
