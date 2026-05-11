"""errors 模块测试."""

from lush_dalx.errors import (
    OPTIMISTIC_LOCK_ERROR_MSG_TRAIT,
    PESSIMISTIC_LOCK_ERROR_MSG_TRAIT,
    DBRetryableError,
)


class TestDBRetryableError:
    def test_default_message(self):
        e = DBRetryableError()
        assert "数据库操作冲突" in str(e)
        assert e.message == "数据库操作冲突,需要重试"

    def test_custom_message(self):
        e = DBRetryableError("custom error")
        assert e.message == "custom error"

    def test_is_pessimistic_lock_error(self):
        e = DBRetryableError(f"something {PESSIMISTIC_LOCK_ERROR_MSG_TRAIT} something")
        assert e.is_pessimistic_lock_retry_error is True
        assert e.is_optimistic_lock_retry_error is False

    def test_is_optimistic_lock_error(self):
        e = DBRetryableError(f"something {OPTIMISTIC_LOCK_ERROR_MSG_TRAIT} something")
        assert e.is_optimistic_lock_retry_error is True
        assert e.is_pessimistic_lock_retry_error is False

    def test_neither_lock_error(self):
        e = DBRetryableError("generic retry")
        assert e.is_pessimistic_lock_retry_error is False
        assert e.is_optimistic_lock_retry_error is False
