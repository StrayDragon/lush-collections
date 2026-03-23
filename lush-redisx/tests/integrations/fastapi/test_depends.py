from __future__ import annotations  # noqa: INP001

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import cast

import pytest
from fastapi import Depends, FastAPI, status
from fastapi.testclient import TestClient
from starlette.requests import Request

from lush_redisx.async_redis import AsyncRedisManager, DebounceResult
from lush_redisx.integrations.fastapi.depends import AsyncRedisManagerDepends
from lush_redisx.integrations.fastapi.depends.idempotency import idempotency_guard_factory
from lush_redisx.integrations.fastapi.depends.rate_limit import debounce_guard_factory


@dataclass
class _FakeDebounceCall:
    key: str
    window_seconds: int


class _FakePrefixedOp:
    def __init__(
        self,
        *,
        debounce_results: list[DebounceResult] | None = None,
        set_results: list[bool] | None = None,
    ) -> None:
        self._debounce_results = list(debounce_results or [])
        self._set_results = list(set_results or [])
        self.debounce_calls: list[_FakeDebounceCall] = []
        self.set_calls: list[tuple[str, str, int | None, bool]] = []

    async def debounce_check_and_set(self, key: str, *, window_seconds: int) -> DebounceResult:
        self.debounce_calls.append(_FakeDebounceCall(key=key, window_seconds=window_seconds))
        if not self._debounce_results:
            raise AssertionError("Unexpected debounce_check_and_set invocation")
        return self._debounce_results.pop(0)

    async def set(self, key: str, value: str, *, expire: int | None, nx: bool) -> bool:
        self.set_calls.append((key, value, expire, nx))
        if self._set_results:
            return self._set_results.pop(0)
        return True


class _FakeRedisManager:
    def __init__(self, prefixed_op: _FakePrefixedOp) -> None:
        self.op_prefixed = prefixed_op


def _build_fastapi_app(dependency: Callable[..., Awaitable[None] | None]) -> FastAPI:
    app = FastAPI()

    @app.post("/trigger", dependencies=[Depends(dependency)])
    async def trigger() -> dict[str, str]:
        return {"status": "ok"}

    return app


def test_debounce_guard_blocks_duplicate_requests() -> None:
    debounce_results = [
        DebounceResult(allowed=True, remaining_seconds=0.0, redis_key="debounce:demo:POST"),
        DebounceResult(allowed=False, remaining_seconds=2.5, redis_key="debounce:demo:POST"),
    ]
    fake_prefixed = _FakePrefixedOp(debounce_results=debounce_results)
    fake_manager = _FakeRedisManager(fake_prefixed)

    def custom_exception_factory(*args, **kwargs):
        from fastapi import HTTPException

        return HTTPException(status_code=429, detail="请稍后重试")

    guard = debounce_guard_factory(
        window_seconds=5,
        redis_dependency=lambda: fake_manager,
        key_builder=lambda request, context: f"debounce:{context}:{request.method}",
        context_dependency=lambda: "demo",
        exception_factory=custom_exception_factory,
    )

    app = _build_fastapi_app(guard)
    client = TestClient(app)

    first = client.post("/trigger")
    assert first.status_code == status.HTTP_200_OK, first.json()
    assert first.json() == {"status": "ok"}

    second = client.post("/trigger")
    assert second.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert second.json()["detail"] == "请稍后重试"

    assert fake_prefixed.debounce_calls[0] == _FakeDebounceCall("debounce:demo:POST", 5)


def test_idempotency_guard_blocks_duplicate_without_header() -> None:
    fake_prefixed = _FakePrefixedOp(set_results=[True, False])
    fake_manager = _FakeRedisManager(fake_prefixed)

    guard = idempotency_guard_factory(
        redis_dependency=lambda: fake_manager,
        ttl_seconds=30,
        user_identifier_getter=lambda _request, _context: "user-1",
    )

    app = _build_fastapi_app(guard)
    client = TestClient(app)

    payload = {"foo": "bar"}

    first = client.post("/trigger", json=payload)
    assert first.status_code == status.HTTP_200_OK, first.json()

    second = client.post("/trigger", json=payload)
    assert second.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    redis_key, value, expire, nx = fake_prefixed.set_calls[0]
    assert redis_key.startswith("idemp:POST:/trigger:user-1:")
    assert value == "1"
    assert expire == 30
    assert nx is True


@pytest.mark.asyncio
async def test_idempotency_guard_supports_custom_exception_factory() -> None:
    fake_prefixed = _FakePrefixedOp(set_results=[False])
    fake_manager = _FakeRedisManager(fake_prefixed)

    class DuplicateSubmissionError(RuntimeError):
        pass

    guard = idempotency_guard_factory(
        redis_dependency=lambda: fake_manager,
        ttl_seconds=10,
        user_identifier_getter=lambda _request, _ctx: "user-2",
        exception_factory=lambda *_: DuplicateSubmissionError("duplicated"),
    )

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "POST",
        "path": "/custom",
        "headers": [],
        "query_string": b"",
        "client": ("testclient", 1234),
        "server": ("testserver", 80),
        "scheme": "http",
    }

    async def receive() -> dict[str, bytes | bool | str]:
        return {"type": "http.request", "body": b'{"hello":"world"}', "more_body": False}

    request = Request(scope, receive)

    with pytest.raises(DuplicateSubmissionError):
        await guard(request, fake_manager, None)


@pytest.mark.asyncio
async def test_async_redis_manager_depends_reads_request_state() -> None:
    scope = {"type": "http", "app": None, "headers": []}
    request = Request(scope)
    sentinel = cast(AsyncRedisManager, object())
    request.state.redis_mgr = sentinel

    resolved = await AsyncRedisManagerDepends.get_async_redis_manager(request)
    assert resolved is sentinel
