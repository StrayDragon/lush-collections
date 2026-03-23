"""互斥锁守卫: 确保同一用户/资源的请求串行执行

用于防止并发请求导致的数据不一致问题,例如:
- 用户快速点击提交按钮多次
- 网络延迟导致的重复请求
- 需要保证操作原子性的场景
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from inspect import Parameter, Signature
from typing import Any, Generic, TypeVar

from fastapi import Depends, HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from structlog import get_logger
from typing_extensions import TypedDict, override

from lush_redisx.async_redis import AsyncRedisManager

TContext = TypeVar("TContext")
RedisDependency = Callable[..., Awaitable[AsyncRedisManager] | AsyncRedisManager]
KeyBuilderCallable = Callable[[Request, Any | None], Awaitable[str] | str]
ExceptionFactoryCallable = Callable[[Request, str, int, Any | None], Exception]

_LOGGER = get_logger(__name__)

DEFAULT_MUTEX_LOCKS_STATE_KEY = "_mutex_locks"


class MutexLockInfo(TypedDict):
    """互斥锁信息.

    Attributes:
        key: Redis 锁键
        redis_mgr: Redis 管理器实例
    """

    key: str
    redis_mgr: AsyncRedisManager


async def _maybe_await_str(value: Awaitable[str] | str) -> str:
    if isinstance(value, str):
        return value
    return await value


class MutexKeyBuilder(ABC, Generic[TContext]):
    """互斥锁键构建器基类.

    用于自定义互斥锁的 Redis 键生成逻辑.

    Type Parameters:
        TContext: 上下文类型,通常是用户 ID 或其他业务标识
    """

    @abstractmethod
    async def build_key(self, request: Request, context: TContext | None = None) -> str:
        """构建互斥锁 Redis key.

        Args:
            request: FastAPI 请求对象
            context: 上下文信息,如用户 ID

        Returns:
            str: Redis 键名
        """


class UserIDMutexKeyBuilder(MutexKeyBuilder[int]):
    """基于用户 ID 的互斥锁键构建器.

    默认的键构建器实现,基于用户 ID 生成锁键.
    如果没有用户 ID,则回退到使用客户端 IP.

    Attributes:
        action: 操作名称,用于区分不同的业务操作
    """

    def __init__(self, action: str) -> None:
        """初始化键构建器.

        Args:
            action: 操作名称,如 "upsert_dispatch"
        """
        self.action = action

    @override
    async def build_key(self, request: Request, context: int | None = None) -> str:
        """构建基于用户 ID 的 Redis 键.

        Args:
            request: FastAPI 请求对象
            context: 用户 ID,如果为 None 则使用客户端 IP

        Returns:
            str: Redis 键名,格式为 "mutex:{action}:user:{user_id}" 或 "mutex:{action}:ip:{ip}"
        """
        if context is None:
            # 如果没有用户 ID,回退到 IP
            client_ip = request.client.host if request.client else "unknown"
            return f"mutex:{self.action}:ip:{client_ip}"
        return f"mutex:{self.action}:user:{context}"


class MutexGuard(Generic[TContext]):
    """互斥锁守卫: 确保同一用户/资源的请求串行执行.

    使用 Redis 分布式锁实现,确保同一时刻只有一个请求在执行.
    如果锁已被占用,立即返回错误,不等待.

    Type Parameters:
        TContext: 上下文类型,通常是用户 ID 或其他业务标识

    Attributes:
        _timeout_seconds: 锁超时时间(秒)
        _redis_dependency: Redis 管理器依赖函数
        _key_builder: 键构建器
        _context_dependency: 上下文依赖函数
        _context_annotation: 上下文类型注解
        _action: 操作名称
        _exception_factory: 异常工厂函数
        _state_key: 在 request.state 中存储锁信息的字段名

    适用场景:
        - 防止用户快速点击提交按钮多次
        - 防止网络延迟导致的重复请求
        - 需要保证操作原子性的场景
        - 防止并发修改同一资源

    与节流的区别:
        - 节流: 时间窗口内只允许一次,即使操作已完成
        - 互斥锁: 只要操作完成就立即释放,可以立即发起下一次请求

    Examples:
        创建一个基于用户 ID 的互斥守卫::

            upsert_mutex = MutexGuard(
                timeout_seconds=30,
                redis_dependency=get_redis_manager,
                action="upsert_dispatch",
                context_dependency=get_user_id,
                context_annotation=int,
            )


            @app.post("/upsert")
            async def upsert(
                data: dict,
                _mutex: None = Depends(upsert_mutex),
            ):
                # 这里的代码只会被同一用户串行执行
                return {"status": "ok"}

        使用自定义异常::

            def custom_exception_factory(*args, **kwargs):
                return MyProjectException("操作正在进行中")


            upsert_mutex = MutexGuard(
                timeout_seconds=30,
                redis_dependency=get_redis_manager,
                action="upsert_dispatch",
                context_dependency=get_user_id,
                context_annotation=int,
                exception_factory=custom_exception_factory,
            )

        自定义 request.state 中的字段名::

            upsert_mutex = MutexGuard(
                timeout_seconds=30,
                redis_dependency=get_redis_manager,
                action="upsert_dispatch",
                state_key="_my_custom_locks",  # 自定义字段名
            )

            # 需要配合自定义中间件使用
            middleware = create_mutex_auto_release_middleware(lambda req: getattr(req.state, "_my_custom_locks", []))
            app.add_middleware(middleware)
    """

    def __init__(
        self,
        timeout_seconds: int,
        *,
        redis_dependency: RedisDependency,
        key_builder: MutexKeyBuilder[TContext] | KeyBuilderCallable | None = None,
        action: str,
        context_dependency: Callable[..., Awaitable[TContext] | TContext] | None = None,
        context_annotation: Any = Any,
        exception_factory: ExceptionFactoryCallable | None = None,
        state_key: str = DEFAULT_MUTEX_LOCKS_STATE_KEY,
    ) -> None:
        """初始化互斥守卫.

        Args:
            timeout_seconds: 锁超时时间(秒),防止死锁.建议设置为业务处理时间的 2-3 倍
            redis_dependency: Redis 管理器依赖函数,返回 AsyncRedisManager 实例
            key_builder: 自定义键构建器.如果不提供,默认使用 UserIDMutexKeyBuilder
            action: 操作名称,用于生成锁键.建议使用描述性名称,如 "upsert_dispatch"
            context_dependency: 上下文依赖函数,通常返回用户 ID 或其他业务标识
            context_annotation: 上下文类型注解,用于 FastAPI 依赖注入
            exception_factory: 自定义异常工厂函数.接收 (request, redis_key, timeout, context) 参数,
                             返回异常对象.如果不提供,默认抛出 HTTPException(409)
            state_key: 在 request.state 中存储锁信息的字段名.默认为 "_mutex_locks".
                      如果需要避免命名冲突,可以自定义此字段名,但需要配合自定义中间件使用

        Raises:
            ValueError: 如果 timeout_seconds <= 0

        Note:
            错误处理方式:
            1. 如果提供 exception_factory: 调用工厂函数并抛出返回的异常
            2. 否则: 抛出 HTTPException(status_code=409, detail="Operation in progress")

            用户可以通过以下方式自定义错误处理:
            - 提供 exception_factory 返回项目特定的异常
            - 或者在 FastAPI 中注册全局异常处理器处理 HTTPException

            自定义 state_key 时的注意事项:
            - 必须配合 create_mutex_auto_release_middleware 创建对应的中间件
            - 中间件需要从相同的 state_key 读取锁信息
        """
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须大于 0")

        self._timeout_seconds = timeout_seconds
        self._redis_dependency = redis_dependency

        # 类型注解使用 Any 以支持不同的 TContext 类型
        # UserIDMutexKeyBuilder 使用 int 类型, 但可以接受 None 并回退到 IP
        self._key_builder: MutexKeyBuilder[Any] | KeyBuilderCallable
        if key_builder is None:
            self._key_builder = UserIDMutexKeyBuilder(action)
        else:
            self._key_builder = key_builder

        self._context_dependency = context_dependency
        self._context_annotation = context_annotation
        self._action = action
        self._exception_factory = exception_factory
        self._state_key = state_key

        # 构建依赖注入签名
        parameters = [
            Parameter(
                "request",
                Parameter.POSITIONAL_OR_KEYWORD,
                annotation=Request,
            ),
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
        """执行互斥检查.

        尝试获取锁,如果失败则抛出异常.
        锁会在请求处理完成后由 MutexAutoReleaseMiddleware 自动释放.

        Args:
            request: FastAPI 请求对象
            redis_mgr: Redis 管理器实例
            context: 上下文信息,如用户 ID

        Raises:
            HTTPException: 如果锁已被占用且未提供 exception_factory
            Exception: 如果锁已被占用且提供了 exception_factory,抛出工厂函数返回的异常

        Note:
            此方法会在 request.state[state_key] 列表中添加锁信息(默认为 request.state._mutex_locks).
            MutexAutoReleaseMiddleware 会在请求结束时自动释放所有锁.
            支持在一个请求中获取多个锁,按照 LIFO 顺序释放.
        """
        redis_key = await self._build_key(request, context)

        # 尝试获取锁(非阻塞)
        acquired = await redis_mgr.op_prefixed.set(
            key=redis_key,
            value="1",
            expire=self._timeout_seconds,
            nx=True,
        )

        if not acquired:
            # 锁已被占用,返回错误
            # 如果提供了自定义异常工厂,使用它
            if self._exception_factory is not None:
                raise self._exception_factory(request, redis_key, self._timeout_seconds, context)

            # 否则抛出标准 HTTPException
            # 用户可以通过全局异常处理器自定义返回格式
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Operation in progress",
            )

        # 锁获取成功,将锁键存储到请求状态中,用于后续释放
        # 支持多个锁,使用列表存储
        if not hasattr(request.state, self._state_key):
            setattr(request.state, self._state_key, [])
        lock_info: MutexLockInfo = {"key": redis_key, "redis_mgr": redis_mgr}
        locks_list: list[MutexLockInfo] = getattr(request.state, self._state_key)
        locks_list.append(lock_info)

    async def _build_key(self, request: Request, context: TContext | None) -> str:
        """构建 Redis 锁键.

        Args:
            request: FastAPI 请求对象
            context: 上下文信息

        Returns:
            str: Redis 锁键
        """
        builder = self._key_builder
        if isinstance(builder, MutexKeyBuilder):
            return await builder.build_key(request, context)

        return await _maybe_await_str(builder(request, context))


def mutex_guard_factory(
    timeout_seconds: int,
    *,
    redis_dependency: RedisDependency,
    key_builder: MutexKeyBuilder[TContext] | KeyBuilderCallable | None = None,
    action: str = "default",
    context_dependency: Callable[..., Awaitable[TContext] | TContext] | None = None,
    context_annotation: Any = Any,
    exception_factory: ExceptionFactoryCallable | None = None,
    state_key: str = DEFAULT_MUTEX_LOCKS_STATE_KEY,
) -> MutexGuard[TContext]:
    """创建互斥守卫的工厂函数.

    Args:
        timeout_seconds: 锁超时时间(秒)
        redis_dependency: Redis 管理器依赖函数
        key_builder: 自定义键构建器
        action: 操作名称
        context_dependency: 上下文依赖函数
        context_annotation: 上下文类型注解
        exception_factory: 自定义异常工厂函数
        state_key: 在 request.state 中存储锁信息的字段名

    Returns:
        MutexGuard[TContext]: 互斥守卫实例

    Examples:
        使用工厂函数创建守卫::

            upsert_mutex = mutex_guard_factory(
                timeout_seconds=30,
                redis_dependency=get_redis,
                action="upsert",
                context_dependency=get_user_id,
                context_annotation=int,
            )

        使用自定义 state_key::

            upsert_mutex = mutex_guard_factory(
                timeout_seconds=30,
                redis_dependency=get_redis,
                action="upsert",
                state_key="_my_locks",
            )
    """
    return MutexGuard(
        timeout_seconds,
        redis_dependency=redis_dependency,
        key_builder=key_builder,
        action=action,
        context_dependency=context_dependency,
        context_annotation=context_annotation,
        exception_factory=exception_factory,
        state_key=state_key,
    )


def create_mutex_auto_release_middleware(
    get_mutex_locks: Callable[[Request], list[MutexLockInfo]],
) -> type[BaseHTTPMiddleware]:
    """创建互斥锁自动释放中间件.

    Args:
        get_mutex_locks: 从 Request 中获取锁信息列表的函数.
                        通常是 lambda req: getattr(req.state, "your_key", [])

    Returns:
        type[BaseHTTPMiddleware]: 中间件类

    Examples:
        使用默认字段名::

            from lush_redisx.integrations.fastapi.middleware import create_mutex_auto_release_middleware
            from lush_redisx.integrations.fastapi.depends.mutex import DEFAULT_MUTEX_LOCKS_STATE_KEY

            middleware = create_mutex_auto_release_middleware(lambda req: getattr(req.state, DEFAULT_MUTEX_LOCKS_STATE_KEY, []))
            app.add_middleware(middleware)

        使用自定义字段名::

            middleware = create_mutex_auto_release_middleware(lambda req: getattr(req.state, "_my_custom_locks", []))
            app.add_middleware(middleware)
    """

    class MutexAutoReleaseMiddleware(BaseHTTPMiddleware):
        """互斥锁自动释放中间件.

        自动释放由 MutexGuard 获取的锁,确保即使发生异常也能正确释放.

        Note:
            此中间件通过 create_mutex_auto_release_middleware 工厂函数创建,
            需要传入 get_mutex_locks 函数来指定从哪个字段读取锁信息.
        """

        @override
        async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
            """处理请求并确保锁被释放.

            Args:
                request: FastAPI 请求对象
                call_next: 下一个中间件或路由处理器

            Returns:
                Response: HTTP 响应
            """
            try:
                return await call_next(request)
            finally:
                await self._release_mutex_lock(request)

        async def _release_mutex_lock(self, request: Request) -> None:
            """释放互斥锁.

            支持释放多个锁,按照获取的逆序释放(LIFO).

            Args:
                request: FastAPI 请求对象
            """
            # 通过传入的 get_mutex_locks 函数获取锁信息
            locks = get_mutex_locks(request)
            if not locks:
                return

            # 按照获取的逆序释放锁(LIFO)
            for lock_info in reversed(locks):
                lock_key = lock_info["key"]
                redis_mgr = lock_info["redis_mgr"]

                try:
                    _ = await redis_mgr.op_prefixed.delete(lock_key)
                    _LOGGER.debug("互斥锁已释放", lock_key=lock_key)
                except Exception:
                    _LOGGER.exception("释放互斥锁失败", lock_key=lock_key)

    return MutexAutoReleaseMiddleware


__all__ = [
    "DEFAULT_MUTEX_LOCKS_STATE_KEY",
    "MutexGuard",
    "MutexKeyBuilder",
    "MutexLockInfo",
    "UserIDMutexKeyBuilder",
    "create_mutex_auto_release_middleware",
    "mutex_guard_factory",
]
