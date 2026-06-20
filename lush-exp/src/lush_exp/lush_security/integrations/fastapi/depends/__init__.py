from collections.abc import Callable
from logging import getLogger
from types import SimpleNamespace
from typing import Any, ClassVar, Protocol, cast

from fastapi import Request, Response
from fastapi.responses import HTMLResponse

from lush_exp.lush_security.csp import CSPManager
from lush_exp.lush_security.exceptions import DecryptionException, TokenExpiredException, TokenInvalidException
from lush_exp.lush_security.jwt_manager import JWTManager


class LoggerLike(Protocol):
    def warning(self, *args: Any, **kwargs: Any) -> Any: ...

    def exception(self, *args: Any, **kwargs: Any) -> Any: ...


class EncryptedParamNaming:
    """加密参数命名约定配置.

    控制 `PageSecurityHelper` 查找加密参数时的命名规则.
    业务项目可自定义后缀和备选前缀来匹配自己的 URL 参数约定.

    Example:
        默认约定 (suffix="_encrypted"):
            task_id_encrypted=xxx

        自定义约定:
            naming = EncryptedParamNaming(
                suffix="_token",
                extra_fallback_prefixes=["cipher_"],
            )
            匹配 task_id_token 或 cipher_task_id
    """

    def __init__(
        self,
        suffix: str = "_encrypted",
        extra_fallback_prefixes: list[str] | None = None,
    ) -> None:
        self.suffix: str = suffix
        # 保留向后兼容: enc_xxx, encrypted_xxx 作为备选前缀
        default_prefixes = ["enc_", "encrypted_"]
        if extra_fallback_prefixes:
            default_prefixes.extend(extra_fallback_prefixes)
        self.fallback_prefixes: list[str] = default_prefixes


class PageSecurityHelper:
    """页面安全助手, 封装常见的解密访问逻辑."""

    def __init__(
        self,
        request: Request,
        jwt_manager: JWTManager,
        param_naming: EncryptedParamNaming | None = None,
    ) -> None:
        self.request: Request = request
        self._jwt_manager: JWTManager = jwt_manager
        self._param_naming: EncryptedParamNaming = param_naming or EncryptedParamNaming()

    @property
    def jwt_manager(self) -> JWTManager:
        """向后兼容的 JWT 管理器访问属性."""
        return self._jwt_manager

    def get_decrypted_id(self, param_name: str, default: int | None = None) -> int | None:
        """按优先级获取单个加密 ID 参数."""
        try:
            if hasattr(self.request.state, "decrypted_params"):
                decrypted_params = cast("dict[str, Any]", self.request.state.decrypted_params)
                if (value := decrypted_params.get(param_name)) is not None:
                    return int(value)

            encrypted_param_names = [f"{param_name}{self._param_naming.suffix}"]
            for prefix in self._param_naming.fallback_prefixes:
                encrypted_param_names.append(f"{prefix}{param_name}")
                encrypted_param_names.append(f"{prefix.rstrip('_')}_{param_name}")

            for encrypted_name in encrypted_param_names:
                if encrypted_value := self.request.query_params.get(encrypted_name):
                    return self._jwt_manager.decrypt_id(encrypted_value, int)

            if normal_value := self.request.query_params.get(param_name):
                return int(normal_value)

        except (DecryptionException, TokenExpiredException, TokenInvalidException):
            return default
        except ValueError:
            return default
        else:
            return default

    def get_decrypted_params(self) -> dict[str, Any]:
        """返回 request.state.decrypted_params 字典."""
        if hasattr(self.request.state, "decrypted_params"):
            return cast("dict[str, Any]", self.request.state.decrypted_params)
        return {}


class PageSecurityFastAPIDepends:
    """FastAPI 页面安全相关依赖工厂.

    组合了 JWT 参数解密和 CSP 安全头设置.
    业务项目可通过 `configure()` 注入自定义的命名约定和设置.
    """

    _config: ClassVar[SimpleNamespace] = SimpleNamespace(
        jwt_manager_provider=None,
        csp_manager_provider=None,
        param_naming=None,
        logger=cast("LoggerLike", getLogger(__name__)),
    )

    @classmethod
    def configure(
        cls,
        *,
        jwt_manager_provider: Callable[[], JWTManager],
        csp_manager_provider: Callable[[], CSPManager],
        param_naming: EncryptedParamNaming | None = None,
        logger: LoggerLike | None = None,
    ) -> None:
        cls._config.jwt_manager_provider = jwt_manager_provider
        cls._config.csp_manager_provider = csp_manager_provider
        cls._config.param_naming = param_naming
        if logger is not None:
            cls._config.logger = logger

    @staticmethod
    def _get_jwt_manager() -> JWTManager:
        provider = cast("Callable[[], JWTManager] | None", PageSecurityFastAPIDepends._config.jwt_manager_provider)
        if provider is None:
            raise RuntimeError("PageSecurityFastAPIDepends 未配置 jwt_manager_provider")
        return provider()

    @staticmethod
    def _get_csp_manager() -> CSPManager:
        provider = cast("Callable[[], CSPManager] | None", PageSecurityFastAPIDepends._config.csp_manager_provider)
        if provider is None:
            raise RuntimeError("PageSecurityFastAPIDepends 未配置 csp_manager_provider")
        return provider()

    @staticmethod
    def _get_param_naming() -> EncryptedParamNaming:
        naming = cast("EncryptedParamNaming | None", PageSecurityFastAPIDepends._config.param_naming)
        return naming or EncryptedParamNaming()

    @staticmethod
    def _get_logger() -> LoggerLike:
        return cast("LoggerLike", PageSecurityFastAPIDepends._config.logger)

    @staticmethod
    def _decrypt_single_param(
        *,
        logger: LoggerLike,
        jwt_manager: JWTManager,
        request: Request,
        encrypted_param: str,
        encrypted_suffix: str,
        decrypted_params: dict[str, Any],
    ) -> None:
        try:
            encrypted_value = request.query_params[encrypted_param]
            original_param = encrypted_param[: -len(encrypted_suffix)]
            decrypted_id = jwt_manager.decrypt_id(encrypted_value, int)
            decrypted_params[original_param] = str(decrypted_id)
        except (DecryptionException, TokenExpiredException, TokenInvalidException) as exc:
            logger.warning(
                "Failed to decrypt parameter '%s': %s",
                encrypted_param,
                str(exc),
                extra={"url": str(request.url), "param": encrypted_param},
            )
        except Exception:
            logger.exception(
                "Unexpected error decrypting parameter",
                extra={"url": str(request.url), "param": encrypted_param},
            )

    @classmethod
    async def process_page_security(cls, request: Request) -> None:
        """解密查询参数并写入 request.state."""
        jwt_manager = cls._get_jwt_manager()
        if not jwt_manager.config.enable_encryption:
            return

        logger = cls._get_logger()
        naming = cls._get_param_naming()

        try:
            query_params = dict(request.query_params)
            decrypted_params: dict[str, Any] = {}

            if jwt_manager.config.encrypt_params_key_name in query_params:
                encrypted_token = query_params[jwt_manager.config.encrypt_params_key_name]
                decrypted_params = jwt_manager.decrypt_query_params(encrypted_token)
            else:
                encrypted_suffix = naming.suffix
                encrypted_id_params = [key for key in query_params if key.endswith(encrypted_suffix)]

                for encrypted_param in encrypted_id_params:
                    cls._decrypt_single_param(
                        logger=logger,
                        jwt_manager=jwt_manager,
                        request=request,
                        encrypted_param=encrypted_param,
                        encrypted_suffix=encrypted_suffix,
                        decrypted_params=decrypted_params,
                    )

            if decrypted_params:
                request.state.decrypted_params = decrypted_params

        except (DecryptionException, TokenExpiredException, TokenInvalidException) as exc:
            logger.warning(
                "Page security decryption failed: %s",
                str(exc),
                extra={"url": str(request.url)},
            )
        except Exception:
            logger.exception(
                "Unexpected error in page security processing",
                extra={"url": str(request.url)},
            )

    @classmethod
    def with_page_security_headers(cls, response: Response) -> Response:
        """为页面响应追加 CSP 头."""
        csp_manager = cls._get_csp_manager()
        if isinstance(response, HTMLResponse) or (
            hasattr(response, "media_type") and response.media_type and "html" in response.media_type
        ):
            nonce = csp_manager.generate_nonce()
            csp_manager.set_security_headers(response, nonce)
            response.headers["X-CSP-Nonce"] = nonce
        return response

    @classmethod
    async def process_page_security_helper(cls, request: Request) -> PageSecurityHelper:
        """构造页面安全助手."""
        return PageSecurityHelper(
            request,
            cls._get_jwt_manager(),
            param_naming=cls._get_param_naming(),
        )


__all__ = [
    "EncryptedParamNaming",
    "LoggerLike",
    "PageSecurityFastAPIDepends",
    "PageSecurityHelper",
]
