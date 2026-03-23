"""JWT 管理器测试."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import BaseModel, Field

from lush_exp.lush_security.exceptions import (
    DecryptionException,
    TokenExpiredException,
    TokenFormatException,
    TokenInvalidException,
)
from lush_exp.lush_security.jwt_manager import (
    JWTConfig,
    JWTManager,
    TokenMetadata,
)


class _TestModel(BaseModel):
    """测试用的 Pydantic 模型."""

    name: str = Field(..., description="名称")
    value: int = Field(..., description="值")


@pytest.fixture
def encrypted_manager() -> JWTManager:
    """启用加密的 JWT 管理器实例."""

    return JWTManager(config=JWTConfig(secret_key="test_secret", enable_encryption=True))  # noqa: S106


@pytest.fixture
def plaintext_manager() -> JWTManager:
    """禁用加密的 JWT 管理器实例."""

    return JWTManager(config=JWTConfig(secret_key="test_secret", enable_encryption=False))  # noqa: S106


class TestJWTConfig:
    def test_default_config(self):
        config = JWTConfig(secret_key="test_secret")  # noqa: S106
        assert config.enable_encryption is True
        assert config.algorithm == "HS256"
        assert config.issuer == "lush_security"
        assert config.default_expire_minutes == 5
        assert config.url_safe_encoding is True

    def test_custom_config(self):
        config = JWTConfig(
            secret_key="custom_secret",  # noqa: S106
            enable_encryption=False,
            algorithm="HS512",
            issuer="custom_issuer",
            default_expire_minutes=10,
            url_safe_encoding=False,
        )
        assert config.enable_encryption is False
        assert config.algorithm == "HS512"
        assert config.issuer == "custom_issuer"
        assert config.default_expire_minutes == 10
        assert config.url_safe_encoding is False


class TestJWTManagerBasic:
    def test_manager_initialization(self, encrypted_manager: JWTManager):
        assert encrypted_manager.config.enable_encryption is True

    def test_custom_config_initialization(self):
        custom_config = JWTConfig(secret_key="custom_secret", enable_encryption=False)  # noqa: S106
        manager = JWTManager(config=custom_config)
        assert manager.config.enable_encryption is False
        assert manager.config.secret_key == "custom_secret"


class TestEncryptDecryptID:
    def test_encrypt_decrypt_int_id(self, encrypted_manager: JWTManager):
        test_id = 12345
        encrypted = encrypted_manager.encrypt_id(test_id)

        assert encrypted != str(test_id)
        assert len(encrypted) > 20

        decrypted = encrypted_manager.decrypt_id(encrypted, int)
        assert decrypted == test_id
        assert isinstance(decrypted, int)

    def test_encrypt_decrypt_int_id_without_encryption(self, plaintext_manager: JWTManager):
        test_id = 12345
        encrypted = plaintext_manager.encrypt_id(test_id)

        assert encrypted == str(test_id)
        decrypted = plaintext_manager.decrypt_id(encrypted, int)
        assert decrypted == test_id

    def test_encrypt_decrypt_str_id(self, encrypted_manager: JWTManager):
        test_id = "user_abc123"
        encrypted = encrypted_manager.encrypt_id(test_id)

        decrypted = encrypted_manager.decrypt_id(encrypted, str)
        assert decrypted == test_id
        assert isinstance(decrypted, str)

    def test_type_inference(self, encrypted_manager: JWTManager):
        test_id = 99999
        encrypted = encrypted_manager.encrypt_id(test_id)

        assert encrypted_manager.decrypt_id(encrypted, int) == test_id
        assert encrypted_manager.decrypt_id(encrypted, str) == str(test_id)

    def test_custom_duration(self, encrypted_manager: JWTManager):
        test_id = 12345
        custom_duration = timedelta(minutes=30)

        encrypted = encrypted_manager.encrypt_id(test_id, duration=custom_duration)
        metadata = encrypted_manager.get_token_metadata(encrypted)

        duration_seconds = (metadata.expires_at - metadata.issued_at).total_seconds()
        expected_seconds = 30 * 60
        assert abs(duration_seconds - expected_seconds) < 2

    def test_custom_expiry_time(self, encrypted_manager: JWTManager):
        test_id = 12345
        now = datetime.now(tz=timezone.utc)
        exp_time = now + timedelta(hours=2)

        encrypted = encrypted_manager.encrypt_id(test_id, exp=exp_time)
        metadata = encrypted_manager.get_token_metadata(encrypted)

        duration_seconds = (metadata.expires_at - metadata.issued_at).total_seconds()
        expected_seconds = 2 * 60 * 60
        assert abs(duration_seconds - expected_seconds) < 2

    def test_default_expiry_is_5_minutes(self, encrypted_manager: JWTManager):
        test_id = 12345
        encrypted = encrypted_manager.encrypt_id(test_id)
        metadata = encrypted_manager.get_token_metadata(encrypted)

        duration_seconds = (metadata.expires_at - metadata.issued_at).total_seconds()
        expected_seconds = 5 * 60
        assert abs(duration_seconds - expected_seconds) < 2


class TestEncryptDecryptModel:
    def test_encrypt_decrypt_model(self, encrypted_manager: JWTManager):
        test_model = _TestModel(name="test", value=123)
        encrypted = encrypted_manager.encrypt_model(test_model, subject="test_subject")

        assert "eyJ" in encrypted or "%7B" in encrypted

        decrypted = encrypted_manager.decrypt_model(encrypted, _TestModel)
        assert decrypted.name == test_model.name
        assert decrypted.value == test_model.value

    def test_encrypt_decrypt_model_without_encryption(self, plaintext_manager: JWTManager):
        test_model = _TestModel(name="test", value=123)
        encrypted = plaintext_manager.encrypt_model(test_model, subject="test_subject")

        data = json.loads(encrypted)
        assert data["name"] == "test"
        assert data["value"] == 123

        decrypted = plaintext_manager.decrypt_model(encrypted, _TestModel)
        assert decrypted == test_model

    def test_decrypt_with_subject_verification(self, encrypted_manager: JWTManager):
        test_model = _TestModel(name="test", value=123)
        encrypted = encrypted_manager.encrypt_model(test_model, subject="correct_subject")

        decrypted = encrypted_manager.decrypt_model(encrypted, _TestModel, verify_subject="correct_subject")
        assert decrypted.name == "test"

        with pytest.raises(TokenInvalidException):
            encrypted_manager.decrypt_model(encrypted, _TestModel, verify_subject="wrong_subject")


class TestEncryptDecryptQueryParams:
    def test_encrypt_decrypt_params(self, encrypted_manager: JWTManager):
        test_params = {"user_id": 123, "action": "view", "timestamp": "2024-01-01"}
        encrypted = encrypted_manager.encrypt_query_params(test_params)

        assert encrypted != json.dumps(test_params)
        assert encrypted_manager.decrypt_query_params(encrypted) == test_params

    def test_encrypt_decrypt_params_without_encryption(self, plaintext_manager: JWTManager):
        test_params = {"user_id": 123}
        encrypted = plaintext_manager.encrypt_query_params(test_params)

        assert json.loads(encrypted) == test_params
        assert plaintext_manager.decrypt_query_params(encrypted) == test_params

    def test_empty_params(self, encrypted_manager: JWTManager):
        empty_params: dict[str, int] = {}
        encrypted = encrypted_manager.encrypt_query_params(empty_params)
        decrypted = encrypted_manager.decrypt_query_params(encrypted)
        assert decrypted == empty_params


class TestGetEncryptKey:
    def test_get_encrypt_id_key(self, encrypted_manager: JWTManager, plaintext_manager: JWTManager):
        original_key = "task_id"
        assert encrypted_manager.get_encrypt_id_key(original_key) == "task_id_encrypted"
        assert plaintext_manager.get_encrypt_id_key(original_key) == original_key

    def test_get_encrypt_model_key(self, encrypted_manager: JWTManager, plaintext_manager: JWTManager):
        original_key = "user_data"
        assert encrypted_manager.get_encrypt_model_key(original_key) == "user_data_token"
        assert plaintext_manager.get_encrypt_model_key(original_key) == original_key


class TestTokenMetadata:
    def test_get_token_metadata(self, encrypted_manager: JWTManager):
        test_id = 12345
        encrypted = encrypted_manager.encrypt_id(test_id)
        metadata = encrypted_manager.get_token_metadata(encrypted)

        assert isinstance(metadata, TokenMetadata)
        assert isinstance(metadata.issued_at, datetime)
        assert isinstance(metadata.expires_at, datetime)
        assert metadata.subject == "encrypted_id"
        assert metadata.expires_at > metadata.issued_at

    def test_metadata_without_encryption(self, plaintext_manager: JWTManager):
        metadata = plaintext_manager.get_token_metadata("dummy_token")
        assert isinstance(metadata, TokenMetadata)
        assert metadata.subject == "unencrypted"


class TestExceptionHandling:
    def test_decrypt_invalid_token(self, encrypted_manager: JWTManager):
        with pytest.raises((TokenInvalidException, DecryptionException)):
            encrypted_manager.decrypt_id("invalid_token_string", int)

    def test_decrypt_expired_token(self, encrypted_manager: JWTManager):
        test_id = 12345
        past_time = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        expired_time = past_time + timedelta(seconds=1)

        encrypted = encrypted_manager.encrypt_id(test_id, iat=past_time, exp=expired_time)

        with pytest.raises(TokenExpiredException):
            encrypted_manager.decrypt_id(encrypted, int)

    def test_decrypt_params_invalid_format(self, encrypted_manager: JWTManager):
        with pytest.raises((TokenFormatException, TokenInvalidException, DecryptionException)):
            encrypted_manager.decrypt_query_params("not_a_valid_token")


class TestEnableEncryptionSwitch:
    def test_encryption_switch_affects_encrypt_id(self, encrypted_manager: JWTManager, plaintext_manager: JWTManager):
        test_id = 12345
        encrypted_token = encrypted_manager.encrypt_id(test_id)
        plain_token = plaintext_manager.encrypt_id(test_id)

        assert encrypted_token != str(test_id)
        assert plain_token == str(test_id)

    def test_encryption_switch_affects_get_key(self, encrypted_manager: JWTManager, plaintext_manager: JWTManager):
        key = "test_key"
        assert encrypted_manager.get_encrypt_id_key(key).endswith("_encrypted")
        assert plaintext_manager.get_encrypt_id_key(key) == key

    def test_manager_respects_config_encryption_setting(self):
        manager = JWTManager(config=JWTConfig(secret_key="test_secret", enable_encryption=False))  # noqa: S106
        assert manager.config.enable_encryption is False
        test_id = 99999
        encrypted = manager.encrypt_id(test_id)
        assert encrypted == str(test_id)


class TestEdgeCases:
    def test_encrypt_zero_id(self, encrypted_manager: JWTManager):
        encrypted = encrypted_manager.encrypt_id(0)
        assert encrypted_manager.decrypt_id(encrypted, int) == 0

    def test_encrypt_negative_id(self, encrypted_manager: JWTManager):
        encrypted = encrypted_manager.encrypt_id(-12345)
        assert encrypted_manager.decrypt_id(encrypted, int) == -12345

    def test_encrypt_large_id(self, encrypted_manager: JWTManager):
        encrypted = encrypted_manager.encrypt_id(9999999999999999)
        assert encrypted_manager.decrypt_id(encrypted, int) == 9999999999999999

    def test_encrypt_empty_string_id(self, encrypted_manager: JWTManager):
        encrypted = encrypted_manager.encrypt_id("")
        assert encrypted_manager.decrypt_id(encrypted, str) == ""

    def test_encrypt_unicode_string_id(self, encrypted_manager: JWTManager):
        test_id = "用户_123_测试"
        encrypted = encrypted_manager.encrypt_id(test_id)
        assert encrypted_manager.decrypt_id(encrypted, str) == test_id


if __name__ == "__main__":  # pragma: no cover - 调用入口
    pytest.main([__file__, "-v", "-s"])
