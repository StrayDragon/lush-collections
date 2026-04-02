from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from logging import getLogger
from types import SimpleNamespace
from urllib.parse import urlencode

import jwt
import pytest
from fastapi import Request, Response
from fastapi.responses import HTMLResponse

from lush_exp.lush_security.csp import CSPManager
from lush_exp.lush_security.integrations.fastapi.depends import PageSecurityFastAPIDepends, PageSecurityHelper
from lush_exp.lush_security.jwt_manager import JWTConfig, JWTManager


async def _receive() -> dict:
    return {"type": "http.request", "body": b"", "more_body": False}


def _make_request(params: dict[str, str]) -> Request:
    query_string = urlencode(params).encode()
    scope = {
        "type": "http",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": query_string,
        "headers": [],
        "client": ("testclient", 123),
        "server": ("testserver", 80),
    }
    return Request(scope, _receive)


class _DummyLogger:
    def __init__(self) -> None:
        self.warnings: list[tuple[tuple, dict]] = []
        self.exceptions: list[tuple[tuple, dict]] = []

    def warning(self, *args, **kwargs):
        self.warnings.append((args, kwargs))

    def exception(self, *args, **kwargs):
        self.exceptions.append((args, kwargs))


@pytest.fixture
def reset_page_security_depends() -> None:
    old = PageSecurityFastAPIDepends._config
    PageSecurityFastAPIDepends._config = SimpleNamespace(
        jwt_manager_provider=None,
        csp_manager_provider=None,
        logger=getLogger("test"),
    )
    try:
        yield
    finally:
        PageSecurityFastAPIDepends._config = old


def _make_jwt_manager(**overrides) -> JWTManager:
    return JWTManager(JWTConfig(secret_key="test_secret", enable_encryption=True, **overrides))  # noqa: S106


def _configure_depends(
    *,
    jwt_manager_provider: Callable[[], JWTManager],
    csp_manager_provider: Callable[[], CSPManager],
    logger: _DummyLogger,
) -> None:
    PageSecurityFastAPIDepends.configure(
        jwt_manager_provider=jwt_manager_provider,
        csp_manager_provider=csp_manager_provider,
        logger=logger,
    )


def test_get_jwt_manager_without_config_raises(reset_page_security_depends) -> None:
    with pytest.raises(RuntimeError):
        _ = PageSecurityFastAPIDepends._get_jwt_manager()

    with pytest.raises(RuntimeError):
        _ = PageSecurityFastAPIDepends._get_csp_manager()


def test_configure_sets_providers_and_logger(reset_page_security_depends) -> None:
    logger = _DummyLogger()
    jwt_mgr = _make_jwt_manager()
    csp_mgr = CSPManager()

    _configure_depends(jwt_manager_provider=lambda: jwt_mgr, csp_manager_provider=lambda: csp_mgr, logger=logger)

    assert PageSecurityFastAPIDepends._get_jwt_manager() is jwt_mgr
    assert PageSecurityFastAPIDepends._get_csp_manager() is csp_mgr
    assert PageSecurityFastAPIDepends._get_logger() is logger


def test_configure_logger_none_does_not_override(reset_page_security_depends) -> None:
    logger1 = _DummyLogger()
    jwt_mgr = _make_jwt_manager()
    csp_mgr = CSPManager()

    _configure_depends(jwt_manager_provider=lambda: jwt_mgr, csp_manager_provider=lambda: csp_mgr, logger=logger1)
    assert PageSecurityFastAPIDepends._get_logger() is logger1

    # logger=None should not override existing logger
    PageSecurityFastAPIDepends.configure(
        jwt_manager_provider=lambda: jwt_mgr,
        csp_manager_provider=lambda: csp_mgr,
        logger=None,
    )
    assert PageSecurityFastAPIDepends._get_logger() is logger1


def test_page_security_helper_get_decrypted_id_prefer_state(reset_page_security_depends) -> None:
    logger = _DummyLogger()
    jwt_mgr = _make_jwt_manager()
    csp_mgr = CSPManager()
    _configure_depends(jwt_manager_provider=lambda: jwt_mgr, csp_manager_provider=lambda: csp_mgr, logger=logger)

    request = _make_request({"task_id": "1"})
    request.state.decrypted_params = {"task_id": "42"}
    helper = PageSecurityHelper(request, jwt_mgr)
    assert helper.get_decrypted_id("task_id") == 42
    assert helper.get_decrypted_params() == {"task_id": "42"}


def test_page_security_helper_get_decrypted_id_from_query_encrypted(reset_page_security_depends) -> None:
    logger = _DummyLogger()
    jwt_mgr = _make_jwt_manager()
    csp_mgr = CSPManager()
    _configure_depends(jwt_manager_provider=lambda: jwt_mgr, csp_manager_provider=lambda: csp_mgr, logger=logger)

    token = jwt_mgr.encrypt_id(123)
    request = _make_request({"task_id_encrypted": token})
    helper = PageSecurityHelper(request, jwt_mgr)
    assert helper.get_decrypted_id("task_id") == 123
    assert helper.get_decrypted_params() == {}


def test_page_security_helper_state_missing_key_falls_back_to_query(reset_page_security_depends) -> None:
    jwt_mgr = _make_jwt_manager()
    token = jwt_mgr.encrypt_id(123)
    request = _make_request({"task_id_encrypted": token})
    request.state.decrypted_params = {"other": "1"}

    helper = PageSecurityHelper(request, jwt_mgr)
    assert helper.get_decrypted_id("task_id") == 123


def test_page_security_helper_get_decrypted_id_from_query_plain(reset_page_security_depends) -> None:
    jwt_mgr = _make_jwt_manager()
    request = _make_request({"task_id": "123"})
    helper = PageSecurityHelper(request, jwt_mgr)
    assert helper.get_decrypted_id("task_id") == 123


def test_page_security_helper_get_decrypted_id_error_returns_default(reset_page_security_depends) -> None:
    jwt_mgr = _make_jwt_manager()
    request = _make_request({"task_id_encrypted": "bad"})
    helper = PageSecurityHelper(request, jwt_mgr)
    assert helper.get_decrypted_id("task_id", default=7) == 7

    request2 = _make_request({})
    helper2 = PageSecurityHelper(request2, jwt_mgr)
    assert helper2.get_decrypted_id("missing", default=None) is None

    request3 = _make_request({"task_id": "not-int"})
    helper3 = PageSecurityHelper(request3, jwt_mgr)
    assert helper3.get_decrypted_id("task_id", default=9) == 9


@pytest.mark.asyncio
async def test_process_page_security_disabled_encryption_noop(reset_page_security_depends) -> None:
    logger = _DummyLogger()
    jwt_mgr = JWTManager(JWTConfig(secret_key="test_secret", enable_encryption=False))  # noqa: S106
    _configure_depends(jwt_manager_provider=lambda: jwt_mgr, csp_manager_provider=CSPManager, logger=logger)

    request = _make_request({"a": "1"})
    await PageSecurityFastAPIDepends.process_page_security(request)
    assert not hasattr(request.state, "decrypted_params")


@pytest.mark.asyncio
async def test_process_page_security_decrypt_encrypted_params_token(reset_page_security_depends) -> None:
    logger = _DummyLogger()
    jwt_mgr = _make_jwt_manager()
    _configure_depends(jwt_manager_provider=lambda: jwt_mgr, csp_manager_provider=CSPManager, logger=logger)

    token = jwt_mgr.encrypt_query_params({"task_id": "123", "x": "y"})
    request = _make_request({jwt_mgr.config.encrypt_params_key_name: token})

    await PageSecurityFastAPIDepends.process_page_security(request)
    assert request.state.decrypted_params == {"task_id": "123", "x": "y"}


@pytest.mark.asyncio
async def test_process_page_security_decrypt_encrypted_ids_and_logs_errors(reset_page_security_depends) -> None:
    logger = _DummyLogger()
    jwt_mgr = _make_jwt_manager()
    _configure_depends(jwt_manager_provider=lambda: jwt_mgr, csp_manager_provider=CSPManager, logger=logger)

    good = jwt_mgr.encrypt_id(1)
    bad_known = "bad-known"  # not a JWT => TokenInvalidException

    now = datetime.now(tz=timezone.utc)
    bad_unknown = jwt.encode(
        {
            "data": {},  # missing required id => TokenFormatException
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "iss": jwt_mgr.config.issuer,
            "sub": "encrypted_id",
            "jti": "id",
        },
        jwt_mgr.config.secret_key,
        algorithm=jwt_mgr.config.algorithm,
    )

    suffix = jwt_mgr.config.encrypt_id_key_suffix
    request = _make_request(
        {
            f"a{suffix}": good,
            f"b{suffix}": bad_known,
            f"c{suffix}": bad_unknown,
        }
    )

    await PageSecurityFastAPIDepends.process_page_security(request)
    assert request.state.decrypted_params["a"] == "1"
    assert len(logger.warnings) == 1
    assert len(logger.exceptions) == 1


@pytest.mark.asyncio
async def test_process_page_security_no_decrypted_params_does_not_set_state(reset_page_security_depends) -> None:
    logger = _DummyLogger()
    jwt_mgr = _make_jwt_manager()
    _configure_depends(jwt_manager_provider=lambda: jwt_mgr, csp_manager_provider=CSPManager, logger=logger)

    suffix = jwt_mgr.config.encrypt_id_key_suffix
    request = _make_request({f"a{suffix}": "bad"})

    await PageSecurityFastAPIDepends.process_page_security(request)
    assert not hasattr(request.state, "decrypted_params")
    assert len(logger.warnings) == 1


@pytest.mark.asyncio
async def test_process_page_security_logs_when_decrypt_query_params_fails(reset_page_security_depends) -> None:
    logger = _DummyLogger()
    jwt_mgr = _make_jwt_manager()
    _configure_depends(jwt_manager_provider=lambda: jwt_mgr, csp_manager_provider=CSPManager, logger=logger)

    now = datetime.now(tz=timezone.utc)
    expired_token = jwt.encode(
        {
            "data": {"params": {"a": 1}},
            "iat": int(now.timestamp()),
            "exp": int((now - timedelta(minutes=1)).timestamp()),
            "iss": jwt_mgr.config.issuer,
            "sub": "encrypted_params",
            "jti": "id",
        },
        jwt_mgr.config.secret_key,
        algorithm=jwt_mgr.config.algorithm,
    )
    request = _make_request({jwt_mgr.config.encrypt_params_key_name: expired_token})
    await PageSecurityFastAPIDepends.process_page_security(request)
    assert len(logger.warnings) == 1

    bad_format_token = jwt.encode(
        {
            "data": {},  # missing params => TokenFormatException
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "iss": jwt_mgr.config.issuer,
            "sub": "encrypted_params",
            "jti": "id",
        },
        jwt_mgr.config.secret_key,
        algorithm=jwt_mgr.config.algorithm,
    )
    request2 = _make_request({jwt_mgr.config.encrypt_params_key_name: bad_format_token})
    await PageSecurityFastAPIDepends.process_page_security(request2)
    assert len(logger.exceptions) == 1


def test_with_page_security_headers_html_and_non_html(reset_page_security_depends) -> None:
    logger = _DummyLogger()
    jwt_mgr = _make_jwt_manager()
    csp_mgr = CSPManager()

    class _FixedNonceCSPManager(CSPManager):
        def generate_nonce(self) -> str:
            return "nonce"

    csp_mgr = _FixedNonceCSPManager()
    _configure_depends(jwt_manager_provider=lambda: jwt_mgr, csp_manager_provider=lambda: csp_mgr, logger=logger)

    resp_html = HTMLResponse("<h1>x</h1>")
    out = PageSecurityFastAPIDepends.with_page_security_headers(resp_html)
    assert out.headers["X-CSP-Nonce"] == "nonce"
    assert "Content-Security-Policy" in out.headers

    resp_media_html = Response(content="x", media_type="text/html")
    out2 = PageSecurityFastAPIDepends.with_page_security_headers(resp_media_html)
    assert out2.headers["X-CSP-Nonce"] == "nonce"

    resp_json = Response(content="{}", media_type="application/json")
    out3 = PageSecurityFastAPIDepends.with_page_security_headers(resp_json)
    assert "X-CSP-Nonce" not in out3.headers


@pytest.mark.asyncio
async def test_process_page_security_helper_builds_helper(reset_page_security_depends) -> None:
    logger = _DummyLogger()
    jwt_mgr = _make_jwt_manager()
    _configure_depends(jwt_manager_provider=lambda: jwt_mgr, csp_manager_provider=CSPManager, logger=logger)

    request = _make_request({"a": "1"})
    helper = await PageSecurityFastAPIDepends.process_page_security_helper(request)
    assert isinstance(helper, PageSecurityHelper)
    assert helper.request is request
    assert helper.jwt_manager is jwt_mgr
