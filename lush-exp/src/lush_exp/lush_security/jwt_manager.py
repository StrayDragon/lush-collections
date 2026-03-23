"""JWT 管理工具."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from typing import Any, Generic, TypeVar, overload
from urllib.parse import quote, unquote
from zoneinfo import ZoneInfo

import jwt
from pydantic import BaseModel, Field, ValidationError
from typing_extensions import Self

from .exceptions import (
    DecryptionException,
    EncryptionException,
    TokenExpiredException,
    TokenFormatException,
    TokenInvalidException,
)

T = TypeVar("T", bound=BaseModel)


class JWTConfig(BaseModel):
    """JWT 配置."""

    secret_key: str = Field(..., description="JWT密钥")
    enable_encryption: bool = Field(default=True, description="是否启用加密")
    algorithm: str = Field(default="HS256", description="加密算法")
    issuer: str = Field(default="lush_security", description="发行者")
    default_expire_minutes: int = Field(default=5, description="默认过期分钟数")
    url_safe_encoding: bool = Field(default=True, description="是否使用URL安全编码")
    timezone: str | None = Field(default=None, description="时区设置")
    encrypt_id_key_suffix: str = Field(default="_encrypted", description="加密ID键名后缀")
    encrypt_params_key_name: str = Field(default="encrypted_params", description="加密参数键名")
    encrypt_model_key_suffix: str = Field(default="_token", description="加密模型键名后缀")


class JWTPayload(BaseModel, Generic[T]):
    """泛型 JWT 载荷."""

    data: T = Field(..., description="用户自定义数据")
    iat: int = Field(..., description="签发时间戳")
    exp: int = Field(..., description="过期时间戳")
    iss: str = Field(..., description="发行者")
    sub: str = Field(..., description="主题标识")
    jti: str | None = Field(default=None, description="JWT唯一标识符")


class TokenMetadata(BaseModel):
    """Token 元数据."""

    issued_at: datetime
    expires_at: datetime
    subject: str
    token_id: str | None = None
    is_expired: bool = False
    time_to_expiry: timedelta | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any], tz: ZoneInfo | None = None) -> Self:
        iat = datetime.fromtimestamp(payload["iat"], tz=tz)
        exp = datetime.fromtimestamp(payload["exp"], tz=tz)
        now = datetime.now(tz=tz)

        return cls(
            issued_at=iat,
            expires_at=exp,
            subject=payload["sub"],
            token_id=payload.get("jti"),
            is_expired=now > exp,
            time_to_expiry=exp - now if now <= exp else None,
        )


class SimpleIDPayload(BaseModel):
    """简单 ID 载荷."""

    id: str = Field(..., description="ID值")


class SimpleParamsPayload(BaseModel):
    """简单参数载荷."""

    params: dict[str, Any] = Field(..., description="参数字典")


class JWTManager:
    """JWT 管理器."""

    def __init__(self, config: JWTConfig) -> None:
        self.config: JWTConfig = config
        self.tz: ZoneInfo | None = ZoneInfo(config.timezone) if config.timezone else None

    def encrypt_model(
        self,
        data: BaseModel,
        subject: str,
        expires_in: timedelta | int | None = None,
        issued_at: datetime | None = None,
        token_id: str | None = None,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        if not self.config.enable_encryption:
            return data.model_dump_json()

        try:
            if issued_at is not None:
                now = issued_at
            elif self.tz is not None:
                now = datetime.now(tz=self.tz)
            else:
                now = datetime.now()

            if expires_in is None:
                exp_time = now + timedelta(minutes=self.config.default_expire_minutes)
            elif isinstance(expires_in, int):
                exp_time = now + timedelta(hours=expires_in)
            else:
                exp_time = now + expires_in

            payload_data = JWTPayload[type(data)](
                data=data,
                iat=int(now.timestamp()),
                exp=int(exp_time.timestamp()),
                iss=self.config.issuer,
                sub=subject,
                jti=token_id or secrets.token_urlsafe(16),
            )

            payload_dict = payload_data.model_dump()
            if extra_claims:
                payload_dict.update(extra_claims)

            token = jwt.encode(payload_dict, self.config.secret_key, algorithm=self.config.algorithm)

            if self.config.url_safe_encoding:
                return quote(token, safe="")

        except Exception as exc:  # pragma: no cover - 实际异常由上层捕获
            raise EncryptionException(f"模型加密失败: {exc}") from exc

        else:
            return token

    def decrypt_model(
        self,
        token: str,
        model_class: type[T],
        verify_subject: str | None = None,
    ) -> T:
        if not self.config.enable_encryption:
            try:
                return model_class.model_validate_json(token)
            except ValidationError as exc:
                raise TokenFormatException(f"模型格式错误: {exc}") from exc

        try:
            if self.config.url_safe_encoding:
                token = unquote(token)

            payload = jwt.decode(
                token,
                self.config.secret_key,
                algorithms=[self.config.algorithm],
                options={
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_iss": True,
                    "verify_sub": bool(verify_subject),
                },
            )

            if payload.get("iss") != self.config.issuer:
                raise jwt.InvalidTokenError("Invalid issuer")  # noqa: TRY301

            if verify_subject and payload.get("sub") != verify_subject:
                raise jwt.InvalidTokenError(f"Invalid subject, expected {verify_subject}")  # noqa: TRY301

            data_dict = payload.get("data")
            if data_dict is None:
                raise jwt.InvalidTokenError("Missing data in token")  # noqa: TRY301

            return model_class.model_validate(data_dict)

        except jwt.ExpiredSignatureError as exc:
            raise TokenExpiredException("JWT token已过期") from exc
        except jwt.InvalidTokenError as exc:
            raise TokenInvalidException(f"无效的JWT token: {exc}") from exc
        except ValidationError as exc:
            raise TokenFormatException(f"模型验证失败: {exc}") from exc
        except Exception as exc:
            raise DecryptionException(f"模型解密失败: {exc}") from exc

    def get_encrypt_model_key(self, key: str) -> str:
        if not self.config.enable_encryption:
            return key
        return f"{key}{self.config.encrypt_model_key_suffix}"

    def encrypt_id(
        self,
        id_value: int | str,
        *,
        duration: timedelta | None = None,
        iat: datetime | None = None,
        exp: datetime | None = None,
    ) -> str:
        if not self.config.enable_encryption:
            return str(id_value)

        try:
            payload = SimpleIDPayload(id=str(id_value))

            if iat is not None:
                issued_at = iat
            elif exp is not None and exp.tzinfo is not None:
                issued_at = datetime.now(tz=exp.tzinfo)
            elif self.tz is not None:
                issued_at = datetime.now(tz=self.tz)
            else:
                issued_at = datetime.now()

            expires_in: timedelta | None = None
            if exp is not None:
                expires_in = exp - issued_at
            elif duration is not None:
                expires_in = duration

            return self.encrypt_model(
                data=payload,
                subject="encrypted_id",
                expires_in=expires_in,
                issued_at=issued_at,
            )

        except Exception as exc:
            raise EncryptionException(f"ID加密失败: {exc}") from exc

    @overload
    def decrypt_id(self, encrypted_token: str, expected_type: type[int]) -> int: ...

    @overload
    def decrypt_id(self, encrypted_token: str, expected_type: type[str]) -> str: ...

    def decrypt_id(self, encrypted_token: str, expected_type: type[int | str] = int) -> int | str:
        if not self.config.enable_encryption:
            return expected_type(encrypted_token)

        try:
            payload = self.decrypt_model(encrypted_token, SimpleIDPayload, verify_subject="encrypted_id")
            return expected_type(payload.id)

        except Exception as exc:
            message = str(exc)
            lower_message = message.lower()
            if "已过期" in message or "expired" in lower_message:
                raise TokenExpiredException("加密ID已过期,请重新获取") from exc
            if "无效" in message or "invalid" in lower_message:
                raise TokenInvalidException(f"无效的加密ID: {exc}") from exc
            if "格式" in message or "format" in lower_message:
                raise TokenFormatException("ID格式错误") from exc
            raise DecryptionException(f"ID解密失败: {exc}") from exc

    def get_encrypt_id_key(self, key: str) -> str:
        if not self.config.enable_encryption:
            return key
        return f"{key}{self.config.encrypt_id_key_suffix}"

    def encrypt_query_params(self, params: dict[str, Any]) -> str:
        if not self.config.enable_encryption:
            return json.dumps(params)

        try:
            payload = SimpleParamsPayload(params=params)
            return self.encrypt_model(data=payload, subject="encrypted_params")
        except Exception as exc:
            raise EncryptionException(f"参数加密失败: {exc}") from exc

    def decrypt_query_params(self, encrypted_token: str) -> dict[str, Any]:
        if not self.config.enable_encryption:
            try:
                return json.loads(encrypted_token)
            except json.JSONDecodeError as exc:
                raise TokenFormatException("参数格式错误") from exc

        try:
            payload = self.decrypt_model(encrypted_token, SimpleParamsPayload, verify_subject="encrypted_params")
        except Exception as exc:
            message = str(exc)
            lower_message = message.lower()
            if "已过期" in message or "expired" in lower_message:
                raise TokenExpiredException("加密参数已过期,请重新获取") from exc
            if "无效" in message or "invalid" in lower_message:
                raise TokenInvalidException(f"无效的加密参数: {exc}") from exc
            raise DecryptionException(f"参数解密失败: {exc}") from exc
        else:
            return payload.params

    def get_token_metadata(self, token: str) -> TokenMetadata:
        try:
            if not self.config.enable_encryption:
                now = datetime.now(tz=self.tz) if self.tz else datetime.now()
                return TokenMetadata(
                    issued_at=now,
                    expires_at=now + timedelta(minutes=self.config.default_expire_minutes),
                    subject="unencrypted",
                )

            if self.config.url_safe_encoding:
                token = unquote(token)

            payload = jwt.decode(
                token,
                self.config.secret_key,
                algorithms=[self.config.algorithm],
                options={"verify_exp": False, "verify_iat": False},
            )

            return TokenMetadata.from_payload(payload, tz=self.tz)

        except jwt.InvalidTokenError as exc:
            raise TokenInvalidException(f"无法解析token元数据: {exc}") from exc


__all__ = [
    "JWTConfig",
    "JWTManager",
    "JWTPayload",
    "SimpleIDPayload",
    "SimpleParamsPayload",
    "TokenMetadata",
]
