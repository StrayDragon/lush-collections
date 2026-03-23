"""共享的 pytest fixtures"""

import os
from collections.abc import AsyncGenerator

import pytest

from lush_redisx import AsyncRedisManager


def _create_test_redis_manager() -> AsyncRedisManager:
    """创建测试用的 Redis 管理器"""
    return AsyncRedisManager(
        host=os.getenv("REDIS_HOST", "127.0.0.1"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        password=os.getenv("REDIS_PASSWORD") or None,
        db=int(os.getenv("REDIS_DB", "0")),
        key_prefix=":test:",
        max_connections=20,
        retry_on_timeout=True,
    )


@pytest.fixture
async def redis_mgr() -> AsyncGenerator[AsyncRedisManager, None]:
    """提供真实的 Redis 管理器用于集成测试"""
    mgr = _create_test_redis_manager()
    try:
        # 快速健康检查,若不可用则跳过测试
        ok = await mgr.health_check()
        if not ok:
            pytest.skip("Redis 未就绪,跳过 Redis 测试")
        yield mgr
    finally:
        await mgr.close()
