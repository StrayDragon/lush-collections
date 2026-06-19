"""MySQL 连接池默认配置 — 独立模块避免循环导入."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MySQLPoolConfig:
    """MySQL 连接池默认配置.

    三级定制方式:
      1. **class-level 子类化**: 子类也需 ``@dataclass`` 装饰
         >>> from dataclasses import field
         >>> @dataclass
         ... class MyPoolConfig(MySQLPoolConfig):
         ...     pool_size: int = field(default=50)
         ...     max_overflow: int = field(default=100)
         >>> class MyManager(AsyncMySQLManager):
         ...     _default_pool_config = MyPoolConfig

      2. **实例级传入**:
         >>> mgr = AsyncMySQLManager(url, pool_config=MySQLPoolConfig(pool_size=10))

      3. **逐参覆盖**: (向后兼容)
         >>> mgr = AsyncMySQLManager(url, pool_size=10)
    """

    pool_size: int = 20
    max_overflow: int = 30
    pool_pre_ping: bool = True
    pool_recycle: int = 3600
    echo: bool = False

    def to_engine_kwargs(self) -> dict[str, Any]:
        """转换为 ``create_engine`` / ``create_async_engine`` 关键字参数."""
        return {
            "pool_size": self.pool_size,
            "max_overflow": self.max_overflow,
            "pool_pre_ping": self.pool_pre_ping,
            "pool_recycle": self.pool_recycle,
            "echo": self.echo,
        }


__all__ = [
    "MySQLPoolConfig",
]
