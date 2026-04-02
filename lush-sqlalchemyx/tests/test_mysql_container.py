import pytest

from lush_sqlalchemyx.mgrs.mysql import AsyncMySQLManager


@pytest.mark.asyncio
async def test_mysql_container_health_check(mysql_endpoint) -> None:
    mgr = AsyncMySQLManager(
        mysql_endpoint.sqlalchemy_url,
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
    )
    try:
        assert await mgr.health_check() is True
    finally:
        await mgr.close()
