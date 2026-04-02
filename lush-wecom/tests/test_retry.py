from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from lush_wecom.utils.retry import aretry_on_error, aretry_on_error_iter, retry_on_error


def test_retry_on_error_success_first_try() -> None:
    calls: list[int] = []

    @retry_on_error(max_retries=3, exceptions=(ValueError,))
    def _f() -> int:
        calls.append(1)
        return 123

    assert _f() == 123
    assert len(calls) == 1


def test_retry_on_error_retries_then_succeeds() -> None:
    calls: list[int] = []
    callback_calls: list[tuple[str, int]] = []

    def _cb(exc: Exception, attempt: int) -> None:
        callback_calls.append((type(exc).__name__, attempt))

    @retry_on_error(max_retries=2, exceptions=(ValueError,), on_retry_callback=_cb)
    def _f() -> int:
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("boom")
        return 7

    assert _f() == 7
    assert len(calls) == 2
    assert callback_calls == [("ValueError", 1)]


def test_retry_on_error_should_retry_false_does_not_retry() -> None:
    calls: list[int] = []

    @retry_on_error(max_retries=2, exceptions=(ValueError,), should_retry=lambda _e: False)
    def _f() -> int:
        calls.append(1)
        raise ValueError("nope")

    with pytest.raises(ValueError):
        _f()
    assert len(calls) == 1


def test_retry_on_error_raises_on_last_attempt() -> None:
    calls: list[int] = []

    @retry_on_error(max_retries=1, exceptions=(ValueError,))
    def _f() -> int:
        calls.append(1)
        raise ValueError("boom")

    with pytest.raises(ValueError):
        _f()
    assert len(calls) == 2


def test_retry_on_error_negative_retries_hits_unreachable_guard() -> None:
    @retry_on_error(max_retries=-1)
    def _f() -> None:
        raise AssertionError("should never be called")

    with pytest.raises(RuntimeError, match="should not reach here"):
        _f()


@pytest.mark.asyncio
async def test_aretry_on_error_retries_then_succeeds() -> None:
    calls: list[int] = []
    callback_calls: list[int] = []

    def _cb(_exc: Exception, attempt: int) -> None:
        callback_calls.append(attempt)

    @aretry_on_error(max_retries=2, exceptions=(ValueError,), on_retry_callback=_cb)
    async def _f() -> int:
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("boom")
        return 5

    assert await _f() == 5
    assert len(calls) == 2
    assert callback_calls == [1]


@pytest.mark.asyncio
async def test_aretry_on_error_raises_on_last_attempt() -> None:
    calls: list[int] = []

    @aretry_on_error(max_retries=1, exceptions=(ValueError,))
    async def _f() -> int:
        calls.append(1)
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await _f()
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_aretry_on_error_should_retry_false_does_not_retry() -> None:
    calls: list[int] = []

    @aretry_on_error(max_retries=1, exceptions=(ValueError,), should_retry=lambda _e: False)
    async def _f() -> int:
        calls.append(1)
        raise ValueError("nope")

    with pytest.raises(ValueError):
        await _f()
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_aretry_on_error_negative_retries_hits_unreachable_guard() -> None:
    @aretry_on_error(max_retries=-1)
    async def _f() -> int:
        raise AssertionError("should never be called")

    with pytest.raises(RuntimeError, match="should not reach here"):
        await _f()


@pytest.mark.asyncio
async def test_aretry_on_error_iter_retries_generator() -> None:
    calls: list[int] = []

    @aretry_on_error_iter(max_retries=1, exceptions=(ValueError,))
    async def _gen() -> AsyncIterator[int]:
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("boom")
        yield 1
        yield 2

    items: list[int] = []
    async for item in _gen():
        items.append(item)

    assert items == [1, 2]
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_aretry_on_error_iter_raises_on_last_attempt_and_calls_callback() -> None:
    callback_calls: list[int] = []
    calls: list[int] = []

    def _cb(_exc: Exception, attempt: int) -> None:
        callback_calls.append(attempt)

    @aretry_on_error_iter(max_retries=1, exceptions=(ValueError,), on_retry_callback=_cb)
    async def _gen() -> AsyncIterator[int]:
        calls.append(1)
        raise ValueError("boom")
        yield 1  # pragma: no cover

    with pytest.raises(ValueError):
        async for _ in _gen():
            pass

    assert len(calls) == 2
    assert callback_calls == [1]


@pytest.mark.asyncio
async def test_aretry_on_error_iter_should_retry_false_does_not_retry() -> None:
    @aretry_on_error_iter(max_retries=1, exceptions=(ValueError,), should_retry=lambda _e: False)
    async def _gen() -> AsyncIterator[int]:
        raise ValueError("nope")
        yield 1  # pragma: no cover

    with pytest.raises(ValueError):
        async for _ in _gen():
            pass


@pytest.mark.asyncio
async def test_aretry_on_error_iter_negative_retries_hits_unreachable_guard() -> None:
    @aretry_on_error_iter(max_retries=-1)
    async def _gen() -> AsyncIterator[int]:
        raise AssertionError("should never be called")
        yield 1  # pragma: no cover

    with pytest.raises(RuntimeError, match="should not reach here"):
        async for _ in _gen():
            pass
