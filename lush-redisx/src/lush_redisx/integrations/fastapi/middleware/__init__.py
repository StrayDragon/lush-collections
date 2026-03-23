from lush_redisx.integrations.fastapi.depends.mutex import DEFAULT_MUTEX_LOCKS_STATE_KEY, create_mutex_auto_release_middleware

# 默认的互斥锁释放中间件,使用默认字段名
MutexReleaseMiddleware = create_mutex_auto_release_middleware(lambda req: getattr(req.state, DEFAULT_MUTEX_LOCKS_STATE_KEY, []))

__all__ = [
    "MutexReleaseMiddleware",
]
