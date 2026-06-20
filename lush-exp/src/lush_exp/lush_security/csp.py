"""内容安全策略(CSP)管理."""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import Response


class CSPManager:
    """CSP 管理器.

    通过 `extra_directives` 参数自定义 CSP 策略指令,
    通过 `extra_headers` 参数追加额外的安全响应头.

    Example:
        业务项目中使用:

            >>> from lush_exp.lush_security.csp import CSPManager
            >>> csp = CSPManager(
            ...     extra_directives=[
            ...         \"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com\",
            ...         \"font-src 'self' https://fonts.gstatic.com\",
            ...         \"img-src 'self' data: https:\",
            ...     ],
            ... )
            >>> csp.set_security_headers(response)
    """

    _DEFAULT_POLICY: list[str] = [
        "default-src 'self'",
        "script-src 'self' 'nonce-{nonce}'",
        "style-src 'self' 'nonce-{nonce}'",
        "img-src 'self' data:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "upgrade-insecure-requests",
    ]

    _BASE_HEADERS: dict[str, str] = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    }

    def __init__(
        self,
        *,
        strict: bool = True,
        extra_directives: list[str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._strict: bool = strict
        self._extra_directives: list[str] = extra_directives or []
        self._extra_headers: dict[str, str] = extra_headers or {}

    def generate_nonce(self) -> str:
        """生成 CSP nonce."""

        return secrets.token_urlsafe(16)

    def build_csp_policy(self, nonce: str) -> list[str]:
        """构建 CSP 策略指令列表.

        Args:
            nonce: CSP nonce 值

        Returns:
            策略指令列表
        """
        policy = list(self._DEFAULT_POLICY)
        # strict=False 时将 script-src 替换为包含 'unsafe-inline' 的版本
        if not self._strict:
            policy = [
                "script-src 'self' 'nonce-{nonce}' 'unsafe-inline'" if line.startswith("script-src") else line
                for line in policy
            ]
        policy.extend(self._extra_directives)
        return [line.format(nonce=nonce) for line in policy]

    def set_security_headers(self, response: Response, nonce: str | None = None) -> None:
        """为响应设置安全相关的 HTTP 头.

        Args:
            response: FastAPI Response 对象
            nonce: CSP nonce, 不传则自动生成
        """
        if nonce is None:
            nonce = self.generate_nonce()

        csp_policy = self.build_csp_policy(nonce)
        response.headers["Content-Security-Policy"] = "; ".join(csp_policy)

        for header, value in {**self._BASE_HEADERS, **self._extra_headers}.items():
            response.headers[header] = value


__all__ = ["CSPManager"]
