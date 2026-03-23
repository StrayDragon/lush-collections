import functools
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def retry_on_error(
    max_retries: int = 3,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    should_retry: Callable[[Exception], bool] | None = None,
    on_retry_callback: Callable[[Exception, int], None] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    通用重试装饰器

    Args:
        max_retries: 最大重试次数
        exceptions: 需要重试的异常类型
        should_retry: 自定义判断是否需要重试的函数
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:  # noqa: PERF203
                    last_exception = e

                    # 如果是最后一次尝试,直接抛出
                    if attempt >= max_retries:
                        raise

                    # 如果有自定义判断函数,检查是否需要重试
                    if should_retry and not should_retry(e):
                        raise

                    # 调用重试回调
                    if on_retry_callback:
                        on_retry_callback(e, attempt + 1)

            if last_exception:
                raise last_exception
            raise RuntimeError("should not reach here")

        return wrapper

    return decorator


def aretry_on_error(
    max_retries: int = 3,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    should_retry: Callable[[Exception], bool] | None = None,
    on_retry_callback: Callable[[Exception, int], None] | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exception: Exception | None = None

            for attempt in range(max_retries + 1):
                try:
                    # 使用 await 来调用原始的异步函数
                    return await func(*args, **kwargs)
                except exceptions as e:  # noqa: PERF203
                    last_exception = e

                    if attempt >= max_retries:
                        raise

                    if should_retry and not should_retry(e):
                        raise

                    if on_retry_callback:
                        on_retry_callback(e, attempt + 1)

            if last_exception:
                raise last_exception
            raise RuntimeError("should not reach here")

        return wrapper

    return decorator


def aretry_on_error_iter(
    max_retries: int = 3,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    should_retry: Callable[[Exception], bool] | None = None,
    on_retry_callback: Callable[[Exception, int], None] | None = None,
) -> Callable[[Callable[P, AsyncIterator[R]]], Callable[P, AsyncIterator[R]]]:
    """
    针对异步生成器(返回 AsyncIterator[R])的重试装饰器.

    装饰后的函数依旧返回 AsyncIterator[R] (调用时无需 await), 满足类型期望.
    每次重试都会重新创建被装饰的异步生成器, 以便恢复流式消费.
    """

    def decorator(func: Callable[P, AsyncIterator[R]]) -> Callable[P, AsyncIterator[R]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[R]:  # async generator function
            last_exception: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    async for item in func(*args, **kwargs):
                        yield item
                    return  # noqa: TRY300
                except exceptions as e:  # noqa: PERF203
                    last_exception = e
                    if attempt >= max_retries:
                        raise
                    if should_retry and not should_retry(e):
                        raise
                    if on_retry_callback:
                        on_retry_callback(e, attempt + 1)
            if last_exception is not None:
                raise last_exception
            else:
                raise RuntimeError("should not reach here")

        # 类型上, async def + yield 定义的 wrapper 是 AsyncIterator 返回函数
        return wrapper

    return decorator
