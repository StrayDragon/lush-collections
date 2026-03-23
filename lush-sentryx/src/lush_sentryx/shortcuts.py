"""Sentryx 离线脚本工具

提供离线脚本和定时任务的 Sentry 支持.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

import sentry_sdk
from typing_extensions import ParamSpec

P = ParamSpec("P")
R = TypeVar("R")


def with_sentry(
    script_name: str | None = None,
    *,
    init_func: Callable[[], bool] | None = None,
    flush_timeout: float = 2.0,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """离线脚本/定时任务的 Sentry 包装装饰器

    为离线脚本和定时任务提供 Sentry 错误追踪支持,自动在脚本结束时 flush 事件.

    Args:
        script_name: 脚本名称,用于 Sentry 标签,默认使用函数名
        init_func: 可选的 Sentry 初始化函数,在脚本开始时调用
        flush_timeout: 刷新超时时间(秒)

    Returns:
        装饰后的函数

    Example:
        >>> from lush_sentryx.offline import with_sentry
        >>> from lush_sentryx.integrations.flask import init_sentry_for_flask
        >>>
        >>> @with_sentry("daily_sync", init_func=lambda: init_sentry_for_flask(...))
        ... def main():
        ...     pass
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if init_func:
                _ = init_func()
            sentry_sdk.set_tag("script", script_name or func.__name__)
            try:
                return func(*args, **kwargs)
            except Exception as e:
                _ = sentry_sdk.capture_exception(e)
                raise
            finally:
                sentry_sdk.flush(timeout=flush_timeout)

        return wrapper  # type: ignore[return-value]

    return decorator


def capture_script_exception(
    exception: Exception,
    *,
    script_name: str | None = None,
    extras: dict[str, Any] | None = None,
    flush_timeout: float = 2.0,
) -> None:
    """手动捕获脚本异常到 Sentry

    Args:
        exception: 要捕获的异常
        script_name: 脚本名称,用于 Sentry 标签
        extras: 额外的上下文数据
        flush_timeout: 刷新超时时间(秒)

    Example:
        >>> try:
        ...     do_something()
        ... except Exception as e:
        ...     capture_script_exception(e, script_name="my_script", extras={"step": "process"})
    """
    if script_name:
        sentry_sdk.set_tag("script", script_name)
    with sentry_sdk.new_scope() as scope:
        if extras:
            for k, v in extras.items():
                scope.set_extra(k, v)
        _ = sentry_sdk.capture_exception(exception)
    sentry_sdk.flush(timeout=flush_timeout)
