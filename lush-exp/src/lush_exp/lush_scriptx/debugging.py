"""调试辅助装饰器."""

from __future__ import annotations

import functools
import pdb  # noqa: T100  # pragma: no cover - 调试专用
import traceback
from collections.abc import Callable, Coroutine
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def debug_async_on_error(func: Callable[P, Coroutine[None, None, R]]) -> Callable[P, Coroutine[None, None, R]]:
    """当协程发生异常时进入调试."""

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover - 调试工具不纳入覆盖率
            print(f"发生异常: {exc}")
            print("完整错误信息:")
            traceback.print_exc()

            debug_choice = input("是否进入调试模式? (y/n, 默认n): ").lower()
            if debug_choice == "y":
                print("进入调试模式,使用 'l' 查看代码,'pp 变量名' 查看变量值,'c' 继续执行,'q' 退出")
                pdb.post_mortem()
            print("脚本执行失败")
            raise

    return wrapper


def debug_on_error(func: Callable[P, R]) -> Callable[P, R]:
    """当同步函数发生异常时进入调试."""

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover - 调试工具不纳入覆盖率
            print(f"发生异常: {exc}")
            print("完整错误信息:")
            traceback.print_exc()

            debug_choice = input("是否进入调试模式? (y/n, 默认n): ").lower()
            if debug_choice == "y":
                print("进入调试模式,使用 'l' 查看代码,'pp 变量名' 查看变量值,'c' 继续执行,'q' 退出")
                pdb.post_mortem()
            print("脚本执行失败")
            raise

    return wrapper


__all__ = [
    "debug_async_on_error",
    "debug_on_error",
]
