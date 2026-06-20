"""CSP(Content Security Policy)模块测试."""

import pytest
from fastapi import Response

from lush_exp.lush_security.csp import CSPManager

CSP_MANAGER = CSPManager()


class TestCSPManager:
    """测试 CSP 管理器"""

    def test_manager_initialization(self):
        """测试管理器初始化"""

        manager = CSPManager()
        assert manager is not None

    def test_manager_initialization_with_strict_mode(self):
        """测试严格模式初始化"""

        manager = CSPManager(strict=True)
        assert manager is not None

    def test_manager_with_extra_directives(self):
        """测试自定义指令初始化"""

        manager = CSPManager(extra_directives=["img-src 'self' https:"])
        policy = manager.build_csp_policy("test")
        assert any("img-src" in d and "https:" in d for d in policy)

    def test_manager_with_extra_headers(self):
        """测试自定义响应头"""

        manager = CSPManager(extra_headers={"Cache-Control": "no-cache"})
        response = Response()
        manager.set_security_headers(response)
        assert response.headers["Cache-Control"] == "no-cache"

    def test_global_csp_manager_instance(self):
        """测试全局 CSP 管理器实例"""

        assert CSP_MANAGER is not None
        assert isinstance(CSP_MANAGER, CSPManager)


class TestGenerateNonce:
    """测试 nonce 生成"""

    def test_generate_nonce_returns_string(self):
        """测试生成的 nonce 是字符串"""

        manager = CSPManager()
        nonce = manager.generate_nonce()

        assert isinstance(nonce, str)
        assert len(nonce) > 0

    def test_generate_nonce_is_urlsafe(self):
        """测试生成的 nonce 是 URL 安全的"""

        manager = CSPManager()
        nonce = manager.generate_nonce()

        allowed_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        assert all(c in allowed_chars for c in nonce)

    def test_generate_nonce_has_sufficient_length(self):
        """测试 nonce 长度足够"""

        manager = CSPManager()
        nonce = manager.generate_nonce()

        assert len(nonce) >= 20

    def test_generate_nonce_is_unique(self):
        """测试每次生成的 nonce 都不同"""

        manager = CSPManager()

        nonces = [manager.generate_nonce() for _ in range(100)]

        assert len(nonces) == len(set(nonces))


class TestSetSecurityHeaders:
    """测试安全头设置"""

    def test_set_headers_with_provided_nonce(self):
        """测试使用提供的 nonce 设置头"""

        manager = CSPManager()
        response = Response()
        test_nonce = "test-nonce-123"

        manager.set_security_headers(response, nonce=test_nonce)

        csp_header = response.headers.get("Content-Security-Policy", "")
        assert f"'nonce-{test_nonce}'" in csp_header

    def test_set_headers_auto_generates_nonce(self):
        """测试自动生成 nonce"""

        manager = CSPManager()
        response = Response()

        manager.set_security_headers(response)

        csp_header = response.headers.get("Content-Security-Policy", "")
        assert "'nonce-" in csp_header

    def test_csp_header_default_src(self):
        """测试 CSP default-src 指令"""

        manager = CSPManager()
        response = Response()

        manager.set_security_headers(response)

        csp_header = response.headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp_header

    def test_csp_header_script_src_dev(self):
        """测试开发环境的 script-src 指令"""

        manager = CSPManager(strict=False)
        response = Response()

        manager.set_security_headers(response, nonce="test")

        csp_header = response.headers["Content-Security-Policy"]
        assert "script-src 'self' 'nonce-test' 'unsafe-inline'" in csp_header

    def test_csp_header_script_src_prod(self):
        """测试生产环境的 script-src 指令"""

        manager = CSPManager(strict=True)
        response = Response()

        manager.set_security_headers(response, nonce="test")

        csp_header = response.headers["Content-Security-Policy"]
        assert "script-src 'self' 'nonce-test'" in csp_header
        assert "'unsafe-inline'" not in csp_header.split(";")[1]

    def test_csp_header_style_src_default(self):
        """测试默认 style-src 指令 (不含 unsafe-inline)"""

        manager = CSPManager(strict=True)
        response = Response()

        manager.set_security_headers(response)

        csp_header = response.headers["Content-Security-Policy"]
        # 默认 style-src 不含 'unsafe-inline'; 业务方通过 extra_directives 添加
        assert "style-src 'self'" in csp_header

    def test_csp_header_style_src_with_extra(self):
        """测试通过 extra_directives 自定义 style-src"""

        manager = CSPManager(
            extra_directives=["style-src 'self' 'unsafe-inline' https://fonts.googleapis.com"],
        )
        response = Response()

        manager.set_security_headers(response, nonce="test")

        csp_header = response.headers["Content-Security-Policy"]
        assert "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com" in csp_header

    def test_csp_header_font_src_with_extra(self):
        """测试通过 extra_directives 自定义 font-src"""

        manager = CSPManager(
            extra_directives=["font-src 'self' https://fonts.gstatic.com"],
        )
        response = Response()

        manager.set_security_headers(response)

        csp_header = response.headers["Content-Security-Policy"]
        assert "font-src 'self' https://fonts.gstatic.com" in csp_header

    def test_csp_header_img_src(self):
        """测试 img-src 指令"""

        manager = CSPManager()
        response = Response()

        manager.set_security_headers(response)

        csp_header = response.headers["Content-Security-Policy"]
        assert "img-src 'self' data:" in csp_header

    def test_csp_header_img_src_with_extra(self):
        """测试通过 extra_directives 扩展 img-src"""

        manager = CSPManager(
            extra_directives=["img-src 'self' data: https:"],
        )
        response = Response()

        manager.set_security_headers(response)

        csp_header = response.headers["Content-Security-Policy"]
        assert "img-src 'self' data: https:" in csp_header

    def test_csp_header_object_src(self):
        """测试禁用 object/embed"""

        manager = CSPManager()
        response = Response()

        manager.set_security_headers(response)

        csp_header = response.headers["Content-Security-Policy"]
        assert "object-src 'none'" in csp_header

    def test_csp_header_frame_ancestors(self):
        """测试防止 iframe 嵌入"""

        manager = CSPManager()
        response = Response()

        manager.set_security_headers(response)

        csp_header = response.headers["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in csp_header

    def test_csp_header_upgrade_insecure_requests(self):
        """测试升级到 HTTPS"""

        manager = CSPManager()
        response = Response()

        manager.set_security_headers(response)

        csp_header = response.headers["Content-Security-Policy"]
        assert "upgrade-insecure-requests" in csp_header

    def test_multiple_extra_directives(self):
        """测试多条额外指令"""

        manager = CSPManager(
            extra_directives=[
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
                "font-src 'self' https://fonts.gstatic.com",
                "img-src 'self' data: https:",
                "connect-src 'self' https://api.example.com",
            ],
        )
        response = Response()
        manager.set_security_headers(response, nonce="test")

        csp_header = response.headers["Content-Security-Policy"]
        assert "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com" in csp_header
        assert "font-src 'self' https://fonts.gstatic.com" in csp_header
        assert "img-src 'self' data: https:" in csp_header
        assert "connect-src 'self' https://api.example.com" in csp_header


class TestOtherSecurityHeaders:
    """测试其他安全头"""

    def test_x_content_type_options_header(self):
        """测试 X-Content-Type-Options 头"""

        manager = CSPManager()
        response = Response()

        manager.set_security_headers(response)

        assert response.headers["X-Content-Type-Options"] == "nosniff"

    def test_x_frame_options_header(self):
        """测试 X-Frame-Options 头"""

        manager = CSPManager()
        response = Response()

        manager.set_security_headers(response)

        assert response.headers["X-Frame-Options"] == "DENY"

    def test_x_xss_protection_header(self):
        """测试 X-XSS-Protection 头"""

        manager = CSPManager()
        response = Response()

        manager.set_security_headers(response)

        assert response.headers["X-XSS-Protection"] == "1; mode=block"

    def test_referrer_policy_header(self):
        """测试 Referrer-Policy 头"""

        manager = CSPManager()
        response = Response()

        manager.set_security_headers(response)

        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_hsts_header(self):
        """测试 Strict-Transport-Security 头"""

        manager = CSPManager()
        response = Response()

        manager.set_security_headers(response)

        hsts_header = response.headers["Strict-Transport-Security"]
        assert "max-age=31536000" in hsts_header
        assert "includeSubDomains" in hsts_header

    def test_extra_headers_are_set(self):
        """测试通过 extra_headers 自定义的响应头被设置"""

        manager = CSPManager(
            extra_headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
        response = Response()

        manager.set_security_headers(response)

        assert response.headers["Cache-Control"] == "no-cache, no-store, must-revalidate"
        assert response.headers["Pragma"] == "no-cache"
        assert response.headers["Expires"] == "0"

    def test_extra_headers_override_base(self):
        """测试 extra_headers 覆盖基础头"""

        manager = CSPManager(
            extra_headers={"X-Frame-Options": "SAMEORIGIN"},
        )
        response = Response()

        manager.set_security_headers(response)

        assert response.headers["X-Frame-Options"] == "SAMEORIGIN"


class TestIntegrationScenarios:
    """测试集成场景"""

    def test_all_base_headers_set_together(self):
        """测试所有基础安全头同时设置"""

        manager = CSPManager()
        response = Response()

        manager.set_security_headers(response)

        expected_headers = [
            "Content-Security-Policy",
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Referrer-Policy",
            "Strict-Transport-Security",
        ]

        for header in expected_headers:
            assert header in response.headers, f"缺少头: {header}"

    def test_all_headers_with_extra(self):
        """测试基础头 + 自定义头同时设置"""

        manager = CSPManager(
            extra_headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
        response = Response()

        manager.set_security_headers(response)

        expected_headers = [
            "Content-Security-Policy",
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Referrer-Policy",
            "Strict-Transport-Security",
            "Cache-Control",
            "Pragma",
            "Expires",
        ]

        for header in expected_headers:
            assert header in response.headers, f"缺少头: {header}"

    def test_multiple_calls_override_headers(self):
        """测试多次调用会覆盖头"""

        manager = CSPManager()
        response = Response()

        manager.set_security_headers(response, nonce="nonce1")
        first_csp = response.headers["Content-Security-Policy"]

        manager.set_security_headers(response, nonce="nonce2")
        second_csp = response.headers["Content-Security-Policy"]

        assert first_csp != second_csp
        assert "nonce-nonce1" in first_csp
        assert "nonce-nonce2" in second_csp

    def test_response_with_existing_headers(self):
        """测试已有其他头的响应"""

        manager = CSPManager()
        response = Response()

        response.headers["Custom-Header"] = "custom-value"
        response.headers["Another-Header"] = "another-value"

        manager.set_security_headers(response)

        assert response.headers["Custom-Header"] == "custom-value"
        assert response.headers["Another-Header"] == "another-value"
        assert "Content-Security-Policy" in response.headers


class TestEdgeCases:
    """测试边界情况"""

    def test_empty_nonce_string(self):
        """测试空 nonce 字符串"""

        manager = CSPManager()
        response = Response()

        manager.set_security_headers(response, nonce="")

        csp_header = response.headers["Content-Security-Policy"]
        assert "'nonce-'" in csp_header

    def test_special_characters_in_nonce(self):
        """测试 nonce 中的特殊字符"""

        manager = CSPManager()
        response = Response()

        special_nonce = "abc-123_XYZ"
        manager.set_security_headers(response, nonce=special_nonce)

        csp_header = response.headers["Content-Security-Policy"]
        assert f"'nonce-{special_nonce}'" in csp_header

    def test_very_long_nonce(self):
        """测试非常长的 nonce"""

        manager = CSPManager()
        response = Response()

        long_nonce = "a" * 1000
        manager.set_security_headers(response, nonce=long_nonce)

        csp_header = response.headers["Content-Security-Policy"]
        assert f"'nonce-{long_nonce}'" in csp_header


class TestSecurityCompliance:
    """测试安全合规性"""

    def test_no_unsafe_eval_in_csp(self):
        """测试 CSP 不包含 unsafe-eval"""

        manager = CSPManager()
        response = Response()

        manager.set_security_headers(response)

        csp_header = response.headers["Content-Security-Policy"]
        assert "'unsafe-eval'" not in csp_header

    def test_no_unsafe_inline_in_prod_scripts(self):
        """测试生产环境脚本不包含 unsafe-inline"""

        manager = CSPManager(strict=True)
        response = Response()

        manager.set_security_headers(response, nonce="test")

        csp_header = response.headers["Content-Security-Policy"]
        for directive in csp_header.split(";"):
            if "script-src" in directive:
                assert "'unsafe-inline'" not in directive

    def test_hsts_long_max_age(self):
        """测试 HSTS 有足够长的 max-age"""

        manager = CSPManager()
        response = Response()

        manager.set_security_headers(response)

        hsts_header = response.headers["Strict-Transport-Security"]
        assert "max-age=31536000" in hsts_header

    def test_frame_protection_enabled(self):
        """测试框架保护启用"""

        manager = CSPManager()
        response = Response()

        manager.set_security_headers(response)

        assert response.headers["X-Frame-Options"] == "DENY"
        csp_header = response.headers["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in csp_header


if __name__ == "__main__":  # pragma: no cover - 调用入口
    pytest.main([__file__, "-v", "-s"])
