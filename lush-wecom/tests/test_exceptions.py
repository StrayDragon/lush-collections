from __future__ import annotations

import httpx
import pytest

from lush_wecom.core.exceptions import InvalidTokenError, WeComAPIError, WeComHTTPError, WeComResponseValidationError


def test_wecom_api_error_formats_errcode_message() -> None:
    err = WeComAPIError("ignored", errcode=40001, errmsg="bad token")
    assert err.errcode == 40001
    assert "errcode: 40001" in str(err)
    assert "errmsg: bad token" in str(err)


def test_wecom_api_error_uses_message_when_no_errcode() -> None:
    err = WeComAPIError("plain message")
    assert err.errcode is None
    assert str(err) == "plain message"


def test_wecom_http_error_wraps_status_error() -> None:
    req = httpx.Request("GET", "https://example.com")
    resp = httpx.Response(500, request=req)
    http_error = httpx.HTTPStatusError("boom", request=req, response=resp)
    err = WeComHTTPError("HTTP 请求失败", http_error)
    assert "HTTP 请求失败" in str(err)
    assert "boom" in str(err)


def test_wecom_response_validation_error_is_exception() -> None:
    err = WeComResponseValidationError("bad")
    assert isinstance(err, Exception)
    assert str(err) == "bad"


def test_invalid_token_error_is_wecom_api_error() -> None:
    err = InvalidTokenError(errcode=40014, errmsg="invalid")
    assert isinstance(err, WeComAPIError)
    assert err.errcode == 40014


def test_invalid_token_error_without_errcode_is_still_ok() -> None:
    err = InvalidTokenError(message="x")
    assert str(err) == "x"


def test_wecom_api_error_raises_in_pytest() -> None:
    with pytest.raises(WeComAPIError):
        raise WeComAPIError("x")
