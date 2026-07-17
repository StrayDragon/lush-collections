"""协议类型 re-export 回归 — sqlalchemyx 抛出的异常须可被 protocol 类型捕获."""

from __future__ import annotations

from lush_dal_protocol.errors import DBRetryableError as ProtocolDBRetryableError
from lush_dal_protocol.utils import filtered_in_sql_values as protocol_filtered_in_sql_values

from lush_sqlalchemyx.base.dal import DBRetryableError, filtered_in_sql_values


def test_db_retryable_error_is_protocol_type() -> None:
    err = DBRetryableError("test")
    assert isinstance(err, ProtocolDBRetryableError)


def test_filtered_in_sql_values_is_protocol_function() -> None:
    assert filtered_in_sql_values is protocol_filtered_in_sql_values
