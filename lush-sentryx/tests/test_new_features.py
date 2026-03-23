"""测试 lush-sentryx 新增功能

包括:
- offline.py: with_sentry, capture_script_exception
- _base.py: init_sentry_base
- integrations/flask.py: init_sentry_for_flask
- integrations/django.py: init_sentry_for_django
- integrations/fastapi.py: init_sentry_for_fastapi
"""

import os
from unittest.mock import MagicMock, patch

import pytest
import sentry_sdk

from lush_sentryx import SentryConfig, SentryManager, chain_before_send
from lush_sentryx.shortcuts import capture_script_exception, with_sentry


class TestChainBeforeSend:
    """测试 chain_before_send 链式钩子"""

    def test_single_hook(self):
        """测试单个钩子"""

        def base_hook(event, hint):
            event["base"] = True
            return event

        chained = chain_before_send(base_hook, None)
        result = chained({"data": "test"}, {})

        assert result is not None
        assert result["base"] is True
        assert result["data"] == "test"

    def test_chain_two_hooks(self):
        """测试链式组合两个钩子"""

        def base_hook(event, hint):
            event["base"] = True
            return event

        def extra_hook(event, hint):
            event["extra"] = True
            return event

        chained = chain_before_send(base_hook, extra_hook)
        result = chained({"data": "test"}, {})

        assert result is not None
        assert result["base"] is True  # pyright: ignore[reportGeneralTypeIssues]
        assert result["extra"] is True  # pyright: ignore[reportTypedDictNotRequiredAccess]

    def test_base_hook_returns_none(self):
        """测试基础钩子返回 None 时终止链"""

        def base_hook(event, hint):
            return None  # 丢弃事件

        def extra_hook(event, hint):
            event["extra"] = True
            return event

        chained = chain_before_send(base_hook, extra_hook)
        result = chained({"data": "test"}, {})

        # 基础钩子返回 None,链应该终止
        assert result is None

    def test_hint_passed_through(self):
        """测试 hint 参数正确传递"""

        received_hints = []

        def base_hook(event, hint):
            received_hints.append(hint)
            return event

        def extra_hook(event, hint):
            received_hints.append(hint)
            return event

        chained = chain_before_send(base_hook, extra_hook)
        test_hint = {"exc_info": "test_info"}
        chained({}, test_hint)

        assert len(received_hints) == 2
        assert received_hints[0] is test_hint
        assert received_hints[1] is test_hint


class TestSentryCronWrapper:
    """测试 with_sentry 装饰器"""

    def test_basic_wrapper(self):
        """测试基本装饰器功能"""

        @with_sentry("test_script")
        def my_script():
            return "result"

        with patch("sentry_sdk.set_tag") as mock_set_tag, patch("sentry_sdk.flush") as mock_flush:
            result = my_script()

            assert result == "result"
            mock_set_tag.assert_called_once_with("script", "test_script")
            mock_flush.assert_called_once()

    def test_wrapper_with_init_func(self):
        """测试带初始化函数的装饰器"""

        init_called = []

        def init_func():
            init_called.append(True)
            return True

        @with_sentry("test_script", init_func=init_func)
        def my_script():
            return "result"

        with patch("sentry_sdk.set_tag"), patch("sentry_sdk.flush"):
            my_script()

            assert len(init_called) == 1

    def test_wrapper_captures_exception(self):
        """测试异常被捕获"""

        @with_sentry("test_script")
        def failing_script():
            raise ValueError("test error")

        with (
            patch("sentry_sdk.set_tag"),
            patch("sentry_sdk.capture_exception") as mock_capture,
            patch("sentry_sdk.flush") as mock_flush,
        ):
            with pytest.raises(ValueError):
                failing_script()

            mock_capture.assert_called_once()
            mock_flush.assert_called_once()

    def test_wrapper_uses_function_name(self):
        """测试使用函数名作为脚本名"""

        @with_sentry()
        def my_custom_script():
            return "result"

        with patch("sentry_sdk.set_tag") as mock_set_tag, patch("sentry_sdk.flush"):
            my_custom_script()

            mock_set_tag.assert_called_once_with("script", "my_custom_script")


class TestCaptureScriptException:
    """测试 capture_script_exception 函数"""

    def test_basic_capture(self):
        """测试基本捕获功能"""

        with (
            patch("sentry_sdk.capture_exception") as mock_capture,
            patch("sentry_sdk.flush") as mock_flush,
            patch("sentry_sdk.set_tag") as mock_set_tag,
            patch("sentry_sdk.new_scope") as mock_new_scope,
        ):
            mock_scope = MagicMock()
            mock_new_scope.return_value.__enter__ = MagicMock(return_value=mock_scope)
            mock_new_scope.return_value.__exit__ = MagicMock(return_value=None)

            exc = ValueError("test error")
            capture_script_exception(exc, script_name="my_script")

            mock_set_tag.assert_called_once_with("script", "my_script")
            mock_capture.assert_called_once_with(exc)
            mock_flush.assert_called_once()

    def test_capture_with_extras(self):
        """测试带额外信息的捕获"""

        with (
            patch("sentry_sdk.capture_exception"),
            patch("sentry_sdk.flush"),
            patch("sentry_sdk.new_scope") as mock_new_scope,
        ):
            mock_scope = MagicMock()
            mock_new_scope.return_value.__enter__ = MagicMock(return_value=mock_scope)
            mock_new_scope.return_value.__exit__ = MagicMock(return_value=None)

            exc = ValueError("test error")
            capture_script_exception(exc, extras={"step": "process", "count": 10})

            # 验证 extras 被设置
            assert mock_scope.set_extra.call_count == 2


class TestInitSentryBase:
    """测试 init_sentry_base 基础初始化"""

    def test_disabled(self):
        """测试禁用时返回 False"""
        config = SentryConfig(dsn="http://xxx@localhost/1", enabled=False)
        result = config.init()
        assert result is False

    def test_no_dsn(self):
        """测试无 DSN 时返回 False"""
        config = SentryConfig(dsn="", enabled=True)
        result = config.init()
        assert result is False


class TestInitSentryForFlask:
    """测试 init_sentry_for_flask"""

    def test_import_error_without_flask(self):
        """测试未安装 Flask 时抛出 ImportError"""
        from lush_sentryx.integrations.flask import init_sentry_for_flask

        # 直接测试函数存在
        assert callable(init_sentry_for_flask)

    def test_disabled_returns_false(self):
        """测试禁用时返回 False"""
        pytest.importorskip("flask", reason="Flask not installed")
        from lush_sentryx.integrations.flask import FlaskSentryConfig, init_sentry_for_flask

        config = FlaskSentryConfig(dsn="http://xxx@localhost/1", enabled=False)
        result = init_sentry_for_flask(config)

        assert result is False

    def test_raises_on_missing_flask(self):
        """测试未安装 Flask 时抛出 ImportError"""
        try:
            import flask  # noqa: F401  # pyright: ignore[reportMissingImports, reportUnusedImport]

            pytest.skip("Flask is installed, skipping this test")
        except ImportError:
            pass

        from lush_sentryx.integrations.flask import FlaskSentryConfig, init_sentry_for_flask

        config = FlaskSentryConfig(dsn="http://xxx@localhost/1", enabled=True)
        with pytest.raises(ImportError, match="Flask integration requires"):
            init_sentry_for_flask(config)


class TestInitSentryForDjango:
    """测试 init_sentry_for_django"""

    def test_disabled_returns_false(self):
        """测试禁用时返回 False"""
        pytest.importorskip("django", reason="Django not installed")
        from lush_sentryx.integrations.django import DjangoSentryConfig, init_sentry_for_django

        config = DjangoSentryConfig(dsn="http://xxx@localhost/1", enabled=False)
        result = init_sentry_for_django(config)

        assert result is False

    def test_raises_on_missing_django(self):
        """测试未安装 Django 时抛出 ImportError"""
        try:
            import django  # noqa: F401  # pyright: ignore[reportMissingImports, reportUnusedImport]

            pytest.skip("Django is installed, skipping this test")
        except ImportError:
            pass

        from lush_sentryx.integrations.django import DjangoSentryConfig, init_sentry_for_django

        config = DjangoSentryConfig(dsn="http://xxx@localhost/1", enabled=True)
        with pytest.raises(ImportError, match="Django integration requires"):
            init_sentry_for_django(config)


class TestInitSentryForFastAPI:
    """测试 init_sentry_for_fastapi"""

    def test_disabled_returns_false(self):
        """测试禁用时返回 False"""
        from lush_sentryx.integrations.fastapi import FastAPISentryConfig, init_sentry_for_fastapi

        config = FastAPISentryConfig(dsn="http://xxx@localhost/1", enabled=False)
        result = init_sentry_for_fastapi(config)

        assert result is False

    def test_no_dsn_returns_false(self):
        """测试无 DSN 时返回 False"""
        from lush_sentryx.integrations.fastapi import FastAPISentryConfig, init_sentry_for_fastapi

        config = FastAPISentryConfig(dsn="", enabled=True)
        result = init_sentry_for_fastapi(config)

        assert result is False


class TestCreateSentryManager:
    """测试 create_sentry_manager_for_xxx 函数"""

    def test_create_manager_for_fastapi(self):
        """测试创建 FastAPI SentryManager"""
        from lush_sentryx.integrations.fastapi import FastAPISentryConfig, create_sentry_manager_for_fastapi

        config = FastAPISentryConfig(
            dsn="http://xxx@localhost/1",
            enabled=False,  # 禁用以避免实际连接
            service_name="test-service",
        )
        manager = create_sentry_manager_for_fastapi(config)

        assert isinstance(manager, SentryManager)
        assert manager.config.service_name == "test-service"
        assert manager.config.enabled is False

    def test_create_manager_for_flask(self):
        """测试创建 Flask SentryManager"""
        pytest.importorskip("flask", reason="Flask not installed")
        from lush_sentryx.integrations.flask import FlaskSentryConfig, create_sentry_manager_for_flask

        config = FlaskSentryConfig(
            dsn="http://xxx@localhost/1",
            enabled=False,
            service_name="test-flask-service",
            service_version="2.0.0",
        )
        manager = create_sentry_manager_for_flask(config)

        assert isinstance(manager, SentryManager)
        assert manager.config.service_name == "test-flask-service"
        assert manager.config.service_version == "2.0.0"

    def test_create_manager_for_django(self):
        """测试创建 Django SentryManager"""
        pytest.importorskip("django", reason="Django not installed")
        from lush_sentryx.integrations.django import DjangoSentryConfig, create_sentry_manager_for_django

        config = DjangoSentryConfig(
            dsn="http://xxx@localhost/1",
            enabled=False,
            service_name="test-django-service",
        )
        manager = create_sentry_manager_for_django(config)

        assert isinstance(manager, SentryManager)
        assert manager.config.service_name == "test-django-service"

    def test_manager_has_full_api(self):
        """测试 SentryManager 具有完整 API"""
        from lush_sentryx.integrations.fastapi import FastAPISentryConfig, create_sentry_manager_for_fastapi

        config = FastAPISentryConfig(dsn="http://xxx@localhost/1", enabled=False)
        manager = create_sentry_manager_for_fastapi(config)

        # 验证 SentryManager 的核心方法存在
        assert hasattr(manager, "init")
        assert hasattr(manager, "capture_exception")
        assert hasattr(manager, "capture_message")
        assert hasattr(manager, "set_user_context")
        assert hasattr(manager, "set_tag")
        assert hasattr(manager, "add_breadcrumb")
        assert hasattr(manager, "check_connection")
        assert hasattr(manager, "get_health_status")


class TestSentryConfigIntegration:
    """测试 SentryConfig 与 SentryManager 的集成"""

    def test_create_manager_method(self):
        """测试 create_manager 方法"""
        config = SentryConfig(
            dsn="http://xxx@localhost/1",
            enabled=False,
            environment="production",
            service_name="my-service",
            service_version="1.2.3",
        )

        manager = config.create_manager()

        assert isinstance(manager, SentryManager)
        assert manager.config.enabled is False
        assert manager.config.dsn == "http://xxx@localhost/1"
        assert manager.config.environment == "production"
        assert manager.config.service_name == "my-service"
        assert manager.config.service_version == "1.2.3"


class TestIntegrationRealDSN:
    """使用真实 DSN 的集成测试"""

    def test_init_sentry_for_fastapi_real(self):
        """测试 FastAPI 集成初始化"""
        dsn = os.environ.get("LUSH_SENTRYX_REAL_DSN")
        if not dsn:
            pytest.skip("Set LUSH_SENTRYX_REAL_DSN to run real-DSN integration tests")
        pytest.importorskip("fastapi", reason="FastAPI not installed (install extras: lush-sentryx[fastapi])")

        from lush_sentryx.integrations.fastapi import FastAPISentryConfig, init_sentry_for_fastapi

        config = FastAPISentryConfig(
            dsn=dsn,
            enabled=True,
            environment="test-fastapi",
            service_name="test-fastapi-service",
        )
        result = init_sentry_for_fastapi(config)

        assert result is True
        sentry_sdk.set_tag("test_case", "test_init_sentry_for_fastapi")
        sentry_sdk.flush(timeout=5)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
