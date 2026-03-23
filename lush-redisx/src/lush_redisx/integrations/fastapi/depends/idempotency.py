"""幂等实现, 支持参数化实例.

注意: 该模块仍在实验阶段, API 可能会变更.
"""


# ruff: noqa: I001

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from hashlib import sha256
from inspect import Parameter, Signature
from typing import Any, ClassVar, Generic, TypeVar

from fastapi import Depends, HTTPException, Request, status
from lush_redisx import AsyncRedisManager, build_cache_key

TContext = TypeVar("TContext")
RedisDependency = Callable[..., Awaitable[AsyncRedisManager] | AsyncRedisManager]
ContextDependency = Callable[..., Awaitable[TContext] | TContext]


async def _maybe_await_str(value: Awaitable[str] | str) -> str:
    if isinstance(value, str):
        return value
    return await value


class IdempotencyGuard(Generic[TContext]):
    """可复用的幂等守卫."""

    _WRITE_METHODS: ClassVar[set[str]] = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(
        self,
        *,
        redis_dependency: RedisDependency,
        ttl_seconds: int,
        write_methods_only: bool = True,
        header_candidates: Sequence[str] | None = None,
        context_dependency: ContextDependency[TContext] | None = None,
        context_annotation: Any = Any,
        user_identifier_getter: Callable[[Request, TContext | None], Awaitable[str] | str] | None = None,
        fallback_body_builder: Callable[[Request, TContext | None], Awaitable[str] | str] | None = None,
        exception_factory: Callable[[Request, str, int, TContext | None], Exception] | None = None,
        cache_prefix: str = "idemp",
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds 必须大于 0")

        self._redis_dependency = redis_dependency
        self._ttl_seconds = ttl_seconds
        self._write_methods_only = write_methods_only
        self._header_candidates = tuple(header_candidates or ("X-Idempotency-Key", "Idempotency-Key"))
        self._context_dependency = context_dependency
        self._context_annotation = context_annotation
        self._user_identifier_getter = user_identifier_getter or self._default_user_identifier
        self._fallback_body_builder = fallback_body_builder or self._default_body_builder
        self._exception_factory = exception_factory or self._default_exception_factory
        self._cache_prefix = cache_prefix

        parameters = [
            Parameter("request", Parameter.POSITIONAL_OR_KEYWORD, annotation=Request),
            Parameter(
                "redis_mgr",
                Parameter.POSITIONAL_OR_KEYWORD,
                default=Depends(self._redis_dependency),
                annotation=AsyncRedisManager,
            ),
        ]

        if self._context_dependency is not None:
            parameters.append(
                Parameter(
                    "context",
                    Parameter.POSITIONAL_OR_KEYWORD,
                    default=Depends(self._context_dependency),
                    annotation=self._context_annotation,
                )
            )

        self.__signature__ = Signature(parameters=parameters)

    async def __call__(
        self,
        request: Request,
        redis_mgr: AsyncRedisManager,
        context: TContext | None = None,
    ) -> None:
        if self._write_methods_only and request.method.upper() not in self._WRITE_METHODS:
            return

        idem_header = self._extract_header(request)
        context_value = context
        user_identifier = await self._resolve_user_identifier(request, context_value)

        if idem_header and idem_header.strip():
            idem_value = idem_header.strip()
        else:
            fallback_material = await self._fallback_key_material(request, user_identifier, context_value)
            idem_value = sha256(fallback_material.encode("utf-8")).hexdigest()

        redis_key = build_cache_key(
            self._cache_prefix,
            request.method.upper(),
            request.url.path,
            user_identifier,
            idem_value,
        )
        created = await redis_mgr.op_prefixed.set(redis_key, "1", expire=self._ttl_seconds, nx=True)

        if created:
            return

        raise self._exception_factory(request, redis_key, self._ttl_seconds, context_value)

    async def _resolve_user_identifier(self, request: Request, context: TContext | None) -> str:
        identifier = self._user_identifier_getter(request, context)
        if isinstance(identifier, str):
            return identifier
        return await identifier

    async def _fallback_key_material(
        self,
        request: Request,
        user_identifier: str,
        context: TContext | None,
    ) -> str:
        body_material = await _maybe_await_str(self._fallback_body_builder(request, context))
        return f"{request.method}:{request.url.path}:{user_identifier}:{body_material}"

    def _extract_header(self, request: Request) -> str | None:
        for header in self._header_candidates:
            value = request.headers.get(header)
            if value:
                return value
        return None

    @staticmethod
    def _default_user_identifier(_request: Request, context: TContext | None) -> str:
        if context is None:
            return "anonymous"
        return str(context)

    @staticmethod
    async def _default_body_builder(request: Request, _context: TContext | None) -> str:
        body_bytes = await request.body()
        return body_bytes.decode("utf-8", "ignore")

    @staticmethod
    def _default_exception_factory(
        _request: Request,
        redis_key: str,
        ttl_seconds: int,
        _context: TContext | None,
    ) -> Exception:
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": "重复提交",
                "redis_key": redis_key,
                "ttl_seconds": ttl_seconds,
            },
        )


def idempotency_guard_factory(
    *,
    redis_dependency: RedisDependency,
    ttl_seconds: int,
    write_methods_only: bool = True,
    header_candidates: Sequence[str] | None = None,
    context_dependency: ContextDependency[TContext] | None = None,
    context_annotation: Any = Any,
    user_identifier_getter: Callable[[Request, TContext | None], Awaitable[str] | str] | None = None,
    fallback_body_builder: Callable[[Request, TContext | None], Awaitable[str] | str] | None = None,
    exception_factory: Callable[[Request, str, int, TContext | None], Exception] | None = None,
    cache_prefix: str = "idemp",
) -> IdempotencyGuard[TContext]:
    """创建幂等守卫实例."""
    return IdempotencyGuard(
        redis_dependency=redis_dependency,
        ttl_seconds=ttl_seconds,
        write_methods_only=write_methods_only,
        header_candidates=header_candidates,
        context_dependency=context_dependency,
        context_annotation=context_annotation,
        user_identifier_getter=user_identifier_getter,
        fallback_body_builder=fallback_body_builder,
        exception_factory=exception_factory,
        cache_prefix=cache_prefix,
    )


__all__ = [
    "IdempotencyGuard",
    "idempotency_guard_factory",
]
