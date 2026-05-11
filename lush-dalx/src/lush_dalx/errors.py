"""DAL 层通用异常定义."""

from __future__ import annotations

from typing import Final

OPTIMISTIC_LOCK_ERROR_MSG_TRAIT: Final[str] = "乐观锁更新失败"
PESSIMISTIC_LOCK_ERROR_MSG_TRAIT: Final[str] = "悲观锁获取失败"


class DBRetryableError(Exception):
    """数据库可重试异常.

    表示一个由于并发冲突导致的、可以通过重试解决的数据库操作异常.
    这类异常不是错误, 而是正常的并发控制机制, 应该被捕获并重试.
    """

    def __init__(self, message: str = "数据库操作冲突,需要重试") -> None:
        super().__init__(message)
        self.message = message

    @property
    def is_pessimistic_lock_retry_error(self) -> bool:
        """是否为悲观锁重试异常."""
        return PESSIMISTIC_LOCK_ERROR_MSG_TRAIT in self.message

    @property
    def is_optimistic_lock_retry_error(self) -> bool:
        """是否为乐观锁重试异常."""
        return OPTIMISTIC_LOCK_ERROR_MSG_TRAIT in self.message
