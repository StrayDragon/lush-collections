"""测试与 Mock 工具."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, Generic, TypeVar

import pydantic
from fastapi.responses import HTMLResponse, JSONResponse

T = TypeVar("T", bound=pydantic.BaseModel)


try:  # pragma: no cover - polyfactory 属于可选依赖
    from polyfactory.factories.pydantic_factory import ModelFactory  # pyright: ignore[reportAssignmentType]
except ImportError:  # pragma: no cover - 兜底定义

    class ModelFactory(Generic[T]):
        """polyfactory 缺失时的占位类型."""


def gen_base_model_factory(model_class: type[T], force_non_null: bool = True) -> ModelFactory[T]:
    """基于 Pydantic 模型生成 polyfactory 工厂."""

    factory_config: dict[str, Any] = {"__model__": model_class}

    if force_non_null:
        factory_config["__allow_none_optionals__"] = False

    factory = type(
        f"{model_class.__name__}Factory",
        (ModelFactory,),
        factory_config,
    )

    return factory  # noqa: RET504 # pyright: ignore[reportReturnType]


def mock_api_with_auto_pydantic_model_gen(**factory_kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """根据函数返回注解自动生成 Pydantic 模型实例."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*_args: Any, **_kwargs: Any) -> Any:
            sig = inspect.signature(func)
            return_type = sig.return_annotation

            if not inspect.isclass(return_type) or not issubclass(return_type, pydantic.BaseModel):
                raise TypeError(f"函数 '{func.__name__}' 的返回注解必须是 pydantic.BaseModel 子类, 当前为: {return_type!r}")

            factory_cls = gen_base_model_factory(return_type, **factory_kwargs)

            return factory_cls.build()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType,reportAttributeAccessIssue ]

        return wrapper

    return decorator


F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def mock_view_by_func(
    mock_handler: Callable[..., Awaitable[HTMLResponse | JSONResponse]],
    enable_mock: bool = True,
) -> Callable[[F], F]:
    """Mock 视图装饰器."""

    def decorator(original_func: F) -> F:
        @wraps(original_func)
        async def wrapper(*args: Any, **kwargs: Any) -> HTMLResponse | JSONResponse:
            if enable_mock:
                return await mock_handler(*args, **kwargs)
            return await original_func(*args, **kwargs)

        return wrapper  # pyright: ignore[reportReturnType]

    return decorator


def mock_api_by_func(
    mock_handler: Callable[..., Awaitable[JSONResponse]],
    enable_mock: bool = True,
) -> Callable[[F], F]:
    """Mock API 装饰器."""

    def decorator(original_func: F) -> F:
        @wraps(original_func)
        async def wrapper(*args: Any, **kwargs: Any) -> JSONResponse:
            if enable_mock:
                return await mock_handler(*args, **kwargs)
            result = await original_func(*args, **kwargs)
            return result if isinstance(result, JSONResponse) else JSONResponse(content=result)

        return wrapper  # pyright: ignore[reportReturnType]

    return decorator


__all__ = [
    "ModelFactory",
    "gen_base_model_factory",
    "mock_api_by_func",
    "mock_api_with_auto_pydantic_model_gen",
    "mock_view_by_func",
]
