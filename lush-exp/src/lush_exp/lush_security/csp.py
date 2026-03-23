"""内容安全策略(CSP)管理."""

from __future__ import annotations

import secrets

from fastapi import Response


class CSPManager:
    """CSP 管理器."""

    def __init__(self, *, strict: bool = False) -> None:
        self._strict: bool = strict

    def generate_nonce(self) -> str:
        """生成 CSP nonce."""

        return secrets.token_urlsafe(16)

    def set_security_headers(self, response: Response, nonce: str | None = None) -> None:
        """为响应设置安全相关的 HTTP 头."""

        if nonce is None:
            nonce = self.generate_nonce()

        csp_policy = [
            "default-src 'self'",
            f"script-src 'self' 'nonce-{nonce}' 'unsafe-inline'",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data: https:",
            "connect-src 'self'",
            "media-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
            "upgrade-insecure-requests",
        ]

        if self._strict:
            csp_policy[1] = f"script-src 'self' 'nonce-{nonce}'"

        response.headers["Content-Security-Policy"] = "; ".join(csp_policy)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"


__all__ = ["CSPManager"]
