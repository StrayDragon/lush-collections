"""Targeted tests to push branch coverage to 100%.

These tests focus on rarely-hit branches and error wrappers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from pydantic import BaseModel, Field

from lush_exp.lush_security.exceptions import (
    DecryptionException,
    EncryptionException,
    TokenExpiredException,
    TokenFormatException,
    TokenInvalidException,
)
from lush_exp.lush_security.jwt_manager import JWTConfig, JWTManager


class _Model(BaseModel):
    name: str = Field(...)
    value: int = Field(...)


def _make_manager(**overrides) -> JWTManager:
    cfg = JWTConfig(
        secret_key="test_secret",  # noqa: S106
        enable_encryption=True,
        **overrides,
    )
    return JWTManager(cfg)


def _encode_payload(*, secret: str, payload: dict) -> str:
    return jwt.encode(payload, secret, algorithm="HS256")


def test_encrypt_model_timezone_extra_claims_and_int_expires() -> None:
    mgr = _make_manager(timezone="UTC", url_safe_encoding=False)
    token = mgr.encrypt_model(
        _Model(name="n", value=1),
        subject="subj",
        expires_in=1,  # int branch: hours
        token_id="fixed",  # noqa: S106
        extra_claims={"role": "admin"},
    )

    # url_safe_encoding=False => raw JWT, not quoted
    assert "." in token
    assert "%2E" not in token

    decoded = mgr.decrypt_model(token, _Model, verify_subject="subj")
    assert decoded == _Model(name="n", value=1)


def test_decrypt_model_plaintext_invalid_json_raises_format() -> None:
    mgr = JWTManager(JWTConfig(secret_key="test_secret", enable_encryption=False))  # noqa: S106
    with pytest.raises(TokenFormatException):
        _ = mgr.decrypt_model("not-json", _Model)


def test_decrypt_model_invalid_issuer_raises_invalid() -> None:
    mgr = _make_manager(url_safe_encoding=False)
    now = datetime.now(tz=timezone.utc)
    payload = {
        "data": {"name": "n", "value": 1},
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "iss": "wrong-issuer",
        "sub": "subj",
        "jti": "id",
    }
    token = _encode_payload(secret=mgr.config.secret_key, payload=payload)
    with pytest.raises(TokenInvalidException):
        _ = mgr.decrypt_model(token, _Model)


def test_decrypt_model_missing_data_raises_invalid() -> None:
    mgr = _make_manager(url_safe_encoding=False)
    now = datetime.now(tz=timezone.utc)
    payload = {
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "iss": mgr.config.issuer,
        "sub": "subj",
        "jti": "id",
    }
    token = _encode_payload(secret=mgr.config.secret_key, payload=payload)
    with pytest.raises(TokenInvalidException):
        _ = mgr.decrypt_model(token, _Model)


def test_decrypt_model_data_validation_error_raises_format() -> None:
    mgr = _make_manager(url_safe_encoding=False)
    now = datetime.now(tz=timezone.utc)
    payload = {
        "data": {"name": "n"},  # missing required field
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "iss": mgr.config.issuer,
        "sub": "subj",
        "jti": "id",
    }
    token = _encode_payload(secret=mgr.config.secret_key, payload=payload)
    with pytest.raises(TokenFormatException):
        _ = mgr.decrypt_model(token, _Model)


def test_decrypt_model_unexpected_error_wrapped() -> None:
    mgr = _make_manager()
    with pytest.raises(DecryptionException):
        _ = mgr.decrypt_model(123, _Model)  # type: ignore[arg-type]


def test_encrypt_id_uses_timezone_when_set() -> None:
    mgr = _make_manager(timezone="UTC")
    token = mgr.encrypt_id(123)
    assert mgr.decrypt_id(token, int) == 123


def test_encrypt_id_wraps_errors() -> None:
    mgr = _make_manager()

    class _BadStr:
        def __str__(self) -> str:
            raise ValueError("boom")

    with pytest.raises(EncryptionException):
        _ = mgr.encrypt_id(_BadStr())  # type: ignore[arg-type]


def test_decrypt_id_format_and_other_errors() -> None:
    mgr = _make_manager(url_safe_encoding=False)
    now = datetime.now(tz=timezone.utc)

    token_missing_id = _encode_payload(
        secret=mgr.config.secret_key,
        payload={
            "data": {},  # missing id
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "iss": mgr.config.issuer,
            "sub": "encrypted_id",
            "jti": "id",
        },
    )
    with pytest.raises(TokenFormatException):
        _ = mgr.decrypt_id(token_missing_id, int)

    token_bad_int = _encode_payload(
        secret=mgr.config.secret_key,
        payload={
            "data": {"id": "not-an-int"},
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "iss": mgr.config.issuer,
            "sub": "encrypted_id",
            "jti": "id",
        },
    )
    with pytest.raises(TokenFormatException):
        _ = mgr.decrypt_id(token_bad_int, int)

    with pytest.raises(DecryptionException):
        _ = _make_manager().decrypt_id(123, int)  # type: ignore[arg-type]


def test_encrypt_query_params_wraps_errors() -> None:
    mgr = _make_manager()

    class _Unjsonable:
        pass

    with pytest.raises(EncryptionException):
        _ = mgr.encrypt_query_params({"a": _Unjsonable()})


def test_decrypt_query_params_plaintext_invalid_json_raises_format() -> None:
    mgr = JWTManager(JWTConfig(secret_key="test_secret", enable_encryption=False))  # noqa: S106
    with pytest.raises(TokenFormatException):
        _ = mgr.decrypt_query_params("not-json")


def test_decrypt_query_params_expired_and_other_errors() -> None:
    mgr = _make_manager(url_safe_encoding=False)
    now = datetime.now(tz=timezone.utc)
    token = _encode_payload(
        secret=mgr.config.secret_key,
        payload={
            "data": {"params": {"a": 1}},
            "iat": int(now.timestamp()),
            "exp": int((now - timedelta(minutes=1)).timestamp()),
            "iss": mgr.config.issuer,
            "sub": "encrypted_params",
            "jti": "id",
        },
    )
    with pytest.raises(TokenExpiredException):
        _ = mgr.decrypt_query_params(token)

    with pytest.raises(DecryptionException):
        _ = _make_manager().decrypt_query_params(123)  # type: ignore[arg-type]


def test_get_token_metadata_url_safe_false_and_invalid() -> None:
    mgr = _make_manager(url_safe_encoding=False)
    token = mgr.encrypt_id(1)
    meta = mgr.get_token_metadata(token)
    assert meta.subject == "encrypted_id"

    with pytest.raises(TokenInvalidException):
        _ = mgr.get_token_metadata("not_a_token")
