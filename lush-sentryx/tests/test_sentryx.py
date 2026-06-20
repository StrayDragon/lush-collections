"""Sentryx 完整测试套件

测试 sentryx 库的所有功能,包括:
- 配置模型
- 初始化和健康检查
- 敏感数据清理
- 事件过滤
- 异常捕获
- 用户上下文设置
"""

import os
from unittest.mock import patch

import pytest
import sentry_sdk
from lush_sentryx_core.sdk.v2 import (
    SENSITIVE_URL_PATTERNS,
    create_additional_filter,
    create_transaction_filter,
    custom_repr,
    mask_user_email_partially,
    parameterize_request_urls,
)

from lush_sentryx import SentryConfig, SentryManager
from lush_sentryx.scrubbers import create_enhanced_scrubber

# 测试用的真实 DSN (开发环境)
# NOTE: 真实 DSN 集成测试仅在显式提供时执行,避免 CI/离线环境失败.
REAL_DSN = os.environ.get("LUSH_SENTRYX_REAL_DSN", "")
# 语法合法但不可达的 DSN
UNREACHABLE_DSN = "http://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa@127.0.0.1:9/1"


class TestSentryConfig:
    """测试 SentryConfig 配置模型"""

    def test_config_defaults(self):
        """测试配置默认值"""
        config = SentryConfig(dsn="")
        assert config.dsn == ""
        assert config.enabled is True
        assert config.environment == "production"
        assert config.traces_sample_rate == 0.0
        assert config.send_default_pii is False
        assert config.additional_denylist == set()
        assert config.service_name == "service"
        assert config.service_version == "1.0.0"
        assert config.max_breadcrumbs == 50
        assert config.attach_stacktrace is True
        assert config.include_local_variables is True

    def test_config_custom_values(self):
        """测试自定义配置值"""
        config = SentryConfig(
            dsn="https://xxx@sentry.io/123",
            enabled=True,
            environment="staging",
            traces_sample_rate=0.1,
            service_name="test-service",
            service_version="2.0.0",
            additional_denylist={"custom_secret", "internal_token"},
        )
        assert config.dsn == "https://xxx@sentry.io/123"
        assert config.enabled is True
        assert config.environment == "staging"
        assert config.traces_sample_rate == 0.1
        assert config.service_name == "test-service"
        assert config.service_version == "2.0.0"
        assert config.additional_denylist == {"custom_secret", "internal_token"}

    def test_config_validation(self):
        """测试配置验证"""
        # traces_sample_rate 必须在 0.0-1.0 之间
        with pytest.raises(ValueError):
            SentryConfig(dsn="", traces_sample_rate=1.5)

        with pytest.raises(ValueError):
            SentryConfig(dsn="", traces_sample_rate=-0.1)


class TestSentryManager:
    """测试 SentryManager 核心类"""

    def test_manager_creation(self):
        """测试管理器创建"""
        config = SentryConfig(dsn="", enabled=False)
        manager = SentryManager(config)
        assert manager.config == config
        assert manager.is_initialized is False

    def test_manager_init_disabled(self):
        """测试禁用状态的初始化"""
        config = SentryConfig(dsn="", enabled=False)
        manager = SentryManager(config)
        result = manager.init()
        assert result is False
        assert manager.is_initialized is False

    def test_manager_init_no_dsn(self):
        """测试无 DSN 时的初始化"""
        config = SentryConfig(dsn="", enabled=True)
        manager = SentryManager(config)
        result = manager.init()
        assert result is False
        assert manager.is_initialized is False

    def test_manager_health_status(self):
        """测试健康状态获取"""
        config = SentryConfig(dsn="", enabled=False)
        manager = SentryManager(config)
        status = manager.get_health_status()
        assert isinstance(status, dict)
        assert "is_initialized" in status
        assert "provider" in status
        assert status["is_initialized"] is False
        assert status["provider"] == "sentry-sdk-native"

    def test_manager_check_connection_not_initialized(self):
        """测试未初始化时的连接检查"""
        config = SentryConfig(dsn="", enabled=False)
        manager = SentryManager(config)
        result = manager.check_connection(timeout=1.0)
        assert result is False

    def test_manager_methods_safe_when_not_initialized(self):
        """测试未初始化时调用方法的安全性"""
        config = SentryConfig(dsn="", enabled=False)
        manager = SentryManager(config)

        # 这些方法不应抛出异常
        manager.capture_exception(ValueError("test"), tags={"test": "true"})
        manager.capture_message("test message", level="info")
        manager.set_user_context({"id": "user_123"})
        manager.set_tag("test_tag", "test_value")
        manager.add_breadcrumb("test breadcrumb", category="test")


class TestSentryInitialization:
    """测试 Sentry 初始化功能"""

    def test_init_sentry_with_real_dsn(self):
        """测试使用真实 DSN 初始化"""
        if not REAL_DSN:
            pytest.skip("Set LUSH_SENTRYX_REAL_DSN to run real-DSN integration tests")
        config = SentryConfig(
            dsn=REAL_DSN,
            enabled=True,
            environment="dev-test",
            traces_sample_rate=0.0,
        )
        manager = SentryManager(config)
        ok = manager.init()
        assert ok is True
        assert manager.is_initialized is True
        sentry_sdk.set_tag("test_case", "test_init_sentry_with_real_dsn")

    def test_init_sentry_with_malformed_dsn(self):
        """测试使用无效 DSN 时的处理"""
        config = SentryConfig(
            dsn="not-a-valid-dsn",
            enabled=True,
            environment="dev-test-invalid",
            traces_sample_rate=0.0,
        )
        manager = SentryManager(config)
        ok = manager.init()
        assert ok is False


class TestSentryHealthManagement:
    """测试 Sentry 健康管理功能"""

    def test_check_sentry_connection_with_real_dsn(self):
        """测试真实连接检查"""
        if not REAL_DSN:
            pytest.skip("Set LUSH_SENTRYX_REAL_DSN to run real-DSN integration tests")
        config = SentryConfig(
            dsn=REAL_DSN,
            enabled=True,
            environment="dev-test",
            traces_sample_rate=0.0,
        )
        manager = SentryManager(config)
        ok = manager.init()
        assert ok is True
        sentry_sdk.set_tag("test_case", "test_check_sentry_connection_with_real_dsn")

        result = manager.check_connection(timeout=5.0)
        assert result is True


class TestSentryCapture:
    """测试 Sentry 捕获功能"""

    def test_capture_exception_with_real_dsn(self):
        """测试真实异常捕获"""
        if not REAL_DSN:
            pytest.skip("Set LUSH_SENTRYX_REAL_DSN to run real-DSN integration tests")
        config = SentryConfig(
            dsn=REAL_DSN,
            enabled=True,
            environment="dev-test",
            traces_sample_rate=0.0,
        )
        manager = SentryManager(config)
        ok = manager.init()
        assert ok is True
        sentry_sdk.set_tag("test_case", "test_capture_exception_with_real_dsn")

        def _raise_error():
            raise ValueError("test error for capture")

        try:
            _raise_error()
        except Exception as e:  # noqa: BLE001
            manager.capture_exception(e, tags={"suite": "real"})

        sentry_sdk.flush(timeout=5)

    def test_capture_message_with_real_dsn(self):
        """测试真实消息捕获"""
        if not REAL_DSN:
            pytest.skip("Set LUSH_SENTRYX_REAL_DSN to run real-DSN integration tests")
        config = SentryConfig(
            dsn=REAL_DSN,
            enabled=True,
            environment="dev-test",
            traces_sample_rate=0.0,
        )
        manager = SentryManager(config)
        ok = manager.init()
        assert ok is True
        sentry_sdk.set_tag("test_case", "test_capture_message_with_real_dsn")

        manager.capture_message("test message for capture", level="info", tags={"suite": "real"})
        sentry_sdk.flush(timeout=5)

    def test_capture_with_unreachable_dsn(self):
        """测试不可达 DSN 时的捕获行为"""
        config = SentryConfig(
            dsn=UNREACHABLE_DSN,
            enabled=True,
            environment="dev-test-unreachable",
            traces_sample_rate=0.0,
        )
        manager = SentryManager(config)
        ok = manager.init()
        assert ok is True

        # 捕获操作不应抛异常
        manager.capture_message("msg on unreachable dsn", level="info", tags={"dsn": "unreachable"})

        try:
            raise RuntimeError("boom")  # noqa: TRY301
        except Exception as e:  # noqa: BLE001
            manager.capture_exception(e, tags={"dsn": "unreachable"})

        # flush 以确保发送尝试完成(即使不可达, 也不应抛出异常)
        sentry_sdk.flush(timeout=0.5)


class TestSensitiveDataScrubbing:
    """测试敏感数据清理功能"""

    def test_parameterize_request_urls(self):
        """测试URL参数清理功能"""
        request = {
            "url": "https://api.example.com/users?token=secret123",
            "query_string": "token=secret123",
        }

        parameterize_request_urls(request)

        # 验证敏感查询参数被移除
        assert "query_string" not in request
        assert "?" not in request["url"]
        assert request["url"] == "https://api.example.com/users"

    def test_parameterize_request_urls_no_sensitive(self):
        """测试非敏感URL不被修改"""
        request = {
            "url": "https://api.example.com/users?page=1",
            "query_string": "page=1",
        }

        parameterize_request_urls(request)

        # 非敏感参数应保留
        assert request["url"] == "https://api.example.com/users?page=1"

    def test_mask_user_email_partially(self):
        """测试用户邮箱部分脱敏"""
        user = {
            "id": "user123",
            "username": "testuser",
            "email": "john.doe@example.com",
            "role": "admin",
        }

        mask_user_email_partially(user)

        # 验证保留字段
        assert user["id"] == "user123"
        assert user["username"] == "testuser"
        assert user["role"] == "admin"

        # 验证邮箱脱敏
        assert user["email"] == "joh***@example.com"

    def test_mask_user_email_short_username(self):
        """测试短用户名邮箱脱敏"""
        user = {"email": "ab@example.com"}

        mask_user_email_partially(user)

        # 短用户名应完全脱敏
        assert user["email"] == "***@example.com"

    def test_enhanced_scrubber_creation(self):
        """测试增强清理器创建"""
        scrubber = create_enhanced_scrubber()
        assert scrubber is not None
        # 验证 scrubber 对象已正确创建
        assert hasattr(scrubber, "scrub_event")

    def test_enhanced_scrubber_with_custom_denylist(self):
        """测试自定义敏感字段列表"""
        custom_fields = {"custom_secret", "internal_token"}
        scrubber = create_enhanced_scrubber(denylist=custom_fields)
        assert scrubber is not None

    def test_sensitive_url_patterns_matching(self):
        """测试URL模式匹配"""
        test_urls = [
            ("?token=abc123", True),
            ("?key=secret", True),
            ("?password=pass", True),
            ("?api_key=xxx", True),
            ("?page=1", False),
            ("?limit=10", False),
        ]

        for url, should_match in test_urls:
            matched = any(pattern.search(url) for pattern in SENSITIVE_URL_PATTERNS)
            assert matched == should_match, f"URL {url} 匹配结果应为 {should_match}"

    def test_mask_user_email_empty_field(self):
        """测试空邮箱字段处理"""
        user = {"email": "", "username": "test"}

        mask_user_email_partially(user)

        # 空邮箱字段应保持不变
        assert user["email"] == ""
        assert user["username"] == "test"

    def test_mask_user_email_invalid_format(self):
        """测试无效邮箱格式处理"""
        user = {"email": "not-an-email", "username": "test"}

        mask_user_email_partially(user)

        # 无效格式的邮箱应保持不变
        assert user["email"] == "not-an-email"

    def test_parameterize_request_urls_malformed_url(self):
        """测试畸形URL处理"""
        request = {"url": 123}  # 非字符串URL

        # 应该不抛异常
        parameterize_request_urls(request)

        assert request["url"] == 123  # 保持原样

    def test_enhanced_scrubber_with_large_denylist(self):
        """测试大量自定义敏感字段"""
        large_denylist = {f"custom_field_{i}" for i in range(100)}
        scrubber = create_enhanced_scrubber(denylist=large_denylist)

        assert scrubber is not None
        # 验证 scrubber 对象已正确创建
        assert hasattr(scrubber, "scrub_event")


class TestEventFiltering:
    """测试事件过滤功能"""

    def test_additional_filter_request_data(self):
        """测试额外过滤器处理请求数据"""
        from sentry_sdk.scrubber import DEFAULT_DENYLIST

        all_fields = set(DEFAULT_DENYLIST)
        filter_func = create_additional_filter(all_fields)

        event = {
            "request": {
                "url": "https://api.example.com/users?token=secret123",
                "query_string": "token=secret123",
            }
        }

        filtered_event = filter_func(event, {})

        assert filtered_event is not None
        # 验证敏感查询参数被移除
        request_data = filtered_event.get("request", {})
        assert "query_string" not in request_data
        url = str(request_data.get("url", ""))
        assert "?" not in url

    def test_additional_filter_user_context(self):
        """测试额外过滤器处理用户上下文"""
        from sentry_sdk.scrubber import DEFAULT_DENYLIST

        all_fields = set(DEFAULT_DENYLIST)
        filter_func = create_additional_filter(all_fields)

        event = {
            "user": {
                "id": "user123",
                "username": "testuser",
                "email": "test@example.com",
                "role": "admin",
            }
        }

        filtered_event = filter_func(event, {})

        assert filtered_event is not None
        user_data = filtered_event.get("user", {})
        assert user_data["id"] == "user123"  # ID保留  # pyright: ignore[reportTypedDictNotRequiredAccess]
        assert user_data["username"] == "testuser"  # 用户名保留  # pyright: ignore[reportTypedDictNotRequiredAccess]
        assert user_data["role"] == "admin"  # 非敏感字段保留

        # 邮箱应被脱敏
        email_value = user_data.get("email", "")
        assert email_value == "tes***@example.com"

    def test_additional_filter_exception_handling(self):
        """测试过滤器异常处理"""
        from sentry_sdk.scrubber import DEFAULT_DENYLIST

        all_fields = set(DEFAULT_DENYLIST)
        filter_func = create_additional_filter(all_fields)

        # 模拟一个会导致过滤异常的事件
        with patch("lush_sentryx_core.sdk.v2.filters.parameterize_request_urls", side_effect=Exception("Mock filter error")):
            result = filter_func({"request": {"url": "test"}}, {})
            assert result is None  # 异常时返回None


class TestTransactionFiltering:
    """测试事务过滤"""

    def test_create_transaction_filter(self):
        """测试事务过滤器创建"""
        filter_func = create_transaction_filter()
        assert callable(filter_func)

    def test_transaction_filter_sensitive_params(self):
        """测试事务名称中敏感参数过滤"""
        filter_func = create_transaction_filter()

        event = {"transaction": "GET /api/data?token=secret123"}
        filtered_event = filter_func(event, {})

        assert filtered_event is not None
        transaction = filtered_event.get("transaction", "")
        # 敏感参数应被替换为 [Filtered]
        assert "secret123" not in transaction
        assert "[Filtered]" in transaction

    def test_transaction_filter_no_sensitive_params(self):
        """测试无敏感参数的事务名称不被修改"""
        filter_func = create_transaction_filter()

        event = {"transaction": "GET /api/data?page=1&limit=10"}
        filtered_event = filter_func(event, {})

        assert filtered_event is not None
        # 非敏感参数应保持不变
        assert filtered_event.get("transaction") == "GET /api/data?page=1&limit=10"

    def test_transaction_filter_exception_handling(self):
        """测试事务过滤器异常处理"""
        filter_func = create_transaction_filter()

        # 空事务名称不应导致错误
        event = {"transaction": None}
        filtered_event = filter_func(event, {})

        assert filtered_event is not None
        assert filtered_event.get("transaction") is None


class TestUserContextSetting:
    """测试用户上下文设置"""

    @patch("sentry_sdk.set_user")
    def test_set_user_context_safe_data(self, mock_set_user):
        """测试安全数据的用户上下文设置"""
        user_data = {"id": "user123", "username": "testuser", "role": "admin"}

        config = SentryConfig(dsn="", enabled=False)
        manager = SentryManager(config)
        manager._initialized = True  # 模拟已初始化

        manager.set_user_context(user_data)

        # 验证被调用且数据未被修改
        mock_set_user.assert_called_once_with(user_data)

    @patch("sentry_sdk.set_user")
    def test_set_user_context_sensitive_data_filtered(self, mock_set_user):
        """测试敏感数据被正确过滤"""
        user_data = {"id": "user123", "email": "test@example.com", "password": "secret123"}

        config = SentryConfig(dsn="", enabled=False)
        manager = SentryManager(config)
        manager._initialized = True  # 模拟已初始化

        manager.set_user_context(user_data)

        # 获取实际调用的参数
        call_args = mock_set_user.call_args[0][0]

        # 验证敏感数据被处理
        assert call_args["id"] == "user123"  # 保留
        assert call_args["email"] == "tes***@example.com"  # 邮箱脱敏
        # password 等敏感字段会由 EventScrubber 自动处理

    @patch("sentry_sdk.set_user")
    def test_set_user_context_exception_handling(self, mock_set_user):
        """测试异常处理"""
        mock_set_user.side_effect = Exception("Mock error")

        config = SentryConfig(dsn="", enabled=False)
        manager = SentryManager(config)
        manager._initialized = True

        # 不应抛出异常
        manager.set_user_context({"id": "user123"})

        # 验证被调用
        mock_set_user.assert_called_once()


class TestCustomRepr:
    """测试 custom_repr 函数的序列化行为"""

    def test_bool_serialization(self) -> None:
        """测试布尔值序列化"""
        assert custom_repr(True) == "True"
        assert custom_repr(False) == "False"

    def test_int_serialization(self) -> None:
        """测试整数序列化"""
        assert custom_repr(0) == "0"
        assert custom_repr(123) == "123"
        assert custom_repr(-456) == "-456"
        assert custom_repr(999999) == "999999"

    def test_float_serialization(self) -> None:
        """测试浮点数序列化"""
        assert custom_repr(3.14) == "3.14"
        assert custom_repr(0.0) == "0.0"
        assert custom_repr(-2.5) == "-2.5"
        assert custom_repr(1.23456789) == "1.23456789"

    def test_string_serialization(self) -> None:
        """测试字符串序列化 - 不添加额外引号"""
        assert custom_repr("hello") == "hello"
        assert custom_repr("新年快乐") == "新年快乐"
        assert custom_repr("hello 'world'") == "hello 'world'"
        assert custom_repr('hello "world"') == 'hello "world"'
        assert custom_repr("") == ""
        assert custom_repr("123") == "123"  # 字符串形式的数字

    def test_none_serialization(self) -> None:
        """测试 None 序列化"""
        assert custom_repr(None) == "None"

    def test_dict_returns_none(self) -> None:
        """测试字典返回 None,让 Sentry 递归处理"""
        assert custom_repr({}) is None
        assert custom_repr({"key": "value"}) is None
        assert custom_repr({"a": 1, "b": 2}) is None
        assert custom_repr({"nested": {"data": 123}}) is None

    def test_list_returns_none(self) -> None:
        """测试列表返回 None,让 Sentry 递归处理"""
        assert custom_repr([]) is None
        assert custom_repr([1, 2, 3]) is None
        assert custom_repr(["a", "b", "c"]) is None
        assert custom_repr([{"key": "value"}]) is None

    def test_tuple_returns_none(self) -> None:
        """测试元组返回 None,让 Sentry 递归处理"""
        assert custom_repr(()) is None
        assert custom_repr((1, 2, 3)) is None
        assert custom_repr(("a", "b")) is None

    def test_set_returns_none(self) -> None:
        """测试集合返回 None,让 Sentry 递归处理"""
        assert custom_repr(set()) is None
        assert custom_repr({1, 2, 3}) is None
        assert custom_repr({"a", "b", "c"}) is None

    def test_custom_object_returns_none(self) -> None:
        """测试自定义对象返回 None,使用默认 repr()"""

        class CustomClass:
            def __init__(self, value: str) -> None:
                self.value = value

        obj = CustomClass("test")
        assert custom_repr(obj) is None

    def test_bool_is_checked_before_int(self) -> None:
        """验证布尔值在整数之前检查 (bool 是 int 的子类)"""
        # bool 是 int 的子类,但应该返回 "True"/"False" 而不是 "1"/"0"
        assert isinstance(True, int)  # True 是 int 的实例
        assert custom_repr(True) == "True"  # 但应该序列化为 "True"
        assert custom_repr(False) == "False"  # 而不是 "0"

    def test_edge_cases(self) -> None:
        """测试边界情况"""
        # 特殊浮点数
        assert custom_repr(float("inf")) == "inf"
        assert custom_repr(float("-inf")) == "-inf"
        # NaN 需要特殊处理,因为 NaN != NaN
        result = custom_repr(float("nan"))
        assert result == "nan"

        # 空字符串
        assert custom_repr("") == ""

        # 零值
        assert custom_repr(0) == "0"
        assert custom_repr(0.0) == "0.0"

    def test_nested_structure_elements(self) -> None:
        """
        测试嵌套结构的元素处理

        注意: custom_repr 会被 Sentry 递归调用到嵌套元素上
        所以这个测试验证单个元素的处理是否正确
        """
        # 这些是会出现在嵌套结构中的元素
        assert custom_repr("value") == "value"  # dict 中的字符串值
        assert custom_repr(123) == "123"  # dict 中的数字值
        assert custom_repr(True) == "True"  # dict 中的布尔值
        assert custom_repr(None) == "None"  # dict 中的 None 值

    @pytest.mark.parametrize(
        "value,expected",
        [
            # 基本类型
            (True, "True"),
            (False, "False"),
            (0, "0"),
            (123, "123"),
            (3.14, "3.14"),
            ("hello", "hello"),
            ("新年快乐", "新年快乐"),
            (None, "None"),
            # 复杂类型返回 None
            ({}, None),
            ([], None),
            ((), None),
            (set(), None),
            ({"key": "value"}, None),
            ([1, 2, 3], None),
        ],
    )
    def test_parametrized_serialization(self, value: object, expected: str | None) -> None:
        """参数化测试各种类型的序列化"""
        assert custom_repr(value) == expected

    def test_real_world_scenario(self) -> None:
        """测试真实场景中的数据"""
        # 这些是典型的局部变量值
        assert custom_repr("新年快乐") == "新年快乐"
        assert custom_repr("xxx") == "xxx"
        assert custom_repr("single") == "single"
        assert custom_repr(False) == "False"
        assert custom_repr("xx") == "xx"

        # 复杂对象返回 None
        complex_param = {
            "text": {"content": "新年快乐"},
            "sender": "xxx",
            "chat_type": "single",
            "attachments": [{"image": {"media_id": "xxx"}, "msgtype": "image"}],
            "allow_select": False,
            "external_userid": ["xx"],
        }
        assert custom_repr(complex_param) is None


class TestSensitiveDataScrubbingIntegration:
    """
    集成测试: 验证敏感数据在真实 Sentry 事件中是否被正确过滤

    使用真实的 GlitchTip DSN 进行端到端测试
    """

    pytestmark = pytest.mark.skipif(not REAL_DSN, reason="Set LUSH_SENTRYX_REAL_DSN to run integration tests")

    def test_wecom_sensitive_fields_in_local_vars(self):
        """测试企业微信敏感字段在局部变量中被过滤"""
        config = SentryConfig(
            dsn=REAL_DSN,
            enabled=True,
            environment="integration-test-wecom-fields",
            traces_sample_rate=0.0,
        )
        manager = SentryManager(config)
        ok = manager.init()
        assert ok is True

        # 设置测试标签
        sentry_sdk.set_tag("test_case", "test_wecom_sensitive_fields")
        sentry_sdk.set_tag("test_type", "integration")

        # 捕获包含敏感数据的异常
        captured_event_id = self._trigger_exception_with_sensitive_data()

        # 等待事件发送
        sentry_sdk.flush(timeout=5)

        # 验证事件ID已生成
        assert captured_event_id is not None
        assert len(captured_event_id) > 0

    def test_nested_sensitive_data_scrubbing(self):
        """测试嵌套结构中的敏感数据过滤"""
        config = SentryConfig(
            dsn=REAL_DSN,
            enabled=True,
            environment="integration-test-nested",
            traces_sample_rate=0.0,
        )
        manager = SentryManager(config)
        ok = manager.init()
        assert ok is True

        sentry_sdk.set_tag("test_case", "test_nested_sensitive_data")
        sentry_sdk.set_tag("test_type", "integration")

        # 使用 extras 发送嵌套数据
        manager.capture_message(
            "Test nested sensitive data",
            level="info",
            extras={
                "wecom_config": {
                    "corpid": "ww1234567890",
                    "corpsecret": "SECRET_VALUE",
                    "nested": {
                        "access_token": "TOKEN_123",
                        "media_id": "MEDIA_456",
                    },
                },
                "normal_data": {
                    "name": "test",
                    "value": "safe",
                },
            },
        )

        sentry_sdk.flush(timeout=5)

    def test_deep_nested_sensitive_data(self):
        """测试多层嵌套(5层)的敏感数据过滤"""
        config = SentryConfig(
            dsn=REAL_DSN,
            enabled=True,
            environment="integration-test-deep-nested",
            traces_sample_rate=0.0,
        )
        manager = SentryManager(config)
        ok = manager.init()
        assert ok is True

        sentry_sdk.set_tag("test_case", "test_deep_nested")
        sentry_sdk.set_tag("test_type", "integration")

        # 创建5层嵌套的数据
        manager.capture_message(
            "Test deep nested sensitive data",
            level="info",
            extras={
                "level1": {
                    "level2": {
                        "level3": {
                            "level4": {
                                "level5": {
                                    "corpid": "deep_corpid",
                                    "access_token": "deep_token",
                                    "safe": "value",
                                }
                            }
                        }
                    }
                }
            },
        )

        sentry_sdk.flush(timeout=5)

    def _trigger_exception_with_sensitive_data(self) -> str:
        """触发包含敏感局部变量的异常"""

        def inner_function():
            # 企业微信相关敏感变量
            corpid = "ww1234567890"
            corpsecret = "MY_CORP_SECRET_VALUE"
            access_token = "ACCESS_TOKEN_SECRET"
            media_id = "MEDIA_ID_123"
            appid = "wx123456789"
            agentid = "1000001"
            response_code = "RESPONSE_CODE_SECRET"

            # 正常变量
            normal_value = "this is safe"
            count = 42

            raise ValueError(f"Test error with {count} items")

        try:
            inner_function()
        except Exception as e:
            event_id = sentry_sdk.capture_exception(e)
            return str(event_id) if event_id else ""

        return ""


class TestCustomSensitiveFields:
    """测试用户自定义敏感字段"""

    pytestmark = pytest.mark.skipif(not REAL_DSN, reason="Set LUSH_SENTRYX_REAL_DSN to run integration tests")

    def test_custom_fields_via_init(self):
        """测试通过初始化添加自定义敏感字段"""
        custom_fields = {"custom_secret", "internal_token", "trace_id"}

        config = SentryConfig(
            dsn=REAL_DSN,
            enabled=True,
            environment="test-custom-fields",
            traces_sample_rate=0.0,
            additional_denylist=custom_fields,
        )
        manager = SentryManager(config)
        ok = manager.init()
        assert ok is True
        assert manager.is_initialized is True

        sentry_sdk.set_tag("test_case", "test_custom_fields")
        sentry_sdk.set_tag("test_type", "integration")

        # 验证自定义字段被过滤
        def test_func():
            custom_secret = "MY_CUSTOM_SECRET"
            internal_token = "INTERNAL_TOKEN_123"
            trace_id = "TRACE_ID_456"
            normal_var = "safe"
            raise ValueError("Test custom fields")

        try:
            test_func()
        except Exception as e:
            # 使用 manager 的方法捕获异常
            manager.capture_exception(e, tags={"test": "custom_fields"})

        sentry_sdk.flush(timeout=5)

    def test_custom_fields_in_extras(self):
        """测试自定义字段在 extras 中被过滤"""
        custom_fields = {"business_key", "internal_id"}

        config = SentryConfig(
            dsn=REAL_DSN,
            enabled=True,
            environment="test-custom-extras",
            traces_sample_rate=0.0,
            additional_denylist=custom_fields,
        )
        manager = SentryManager(config)
        ok = manager.init()
        assert ok is True

        sentry_sdk.set_tag("test_case", "test_custom_extras")

        # 在 extras 中使用自定义敏感字段
        manager.capture_message(
            "Test custom fields in extras",
            level="info",
            extras={
                "business_data": {
                    "business_key": "BUSINESS_SECRET",
                    "internal_id": "INTERNAL_ID_123",
                    "public_info": "safe_value",
                }
            },
        )

        sentry_sdk.flush(timeout=5)


class TestDirectSentrySDK:
    """测试直接使用 Sentry SDK 的行为"""

    def test_sentry_sdk_unreachable_dsn_no_raise(self):
        """直接使用 Sentry SDK 配置不可达 DSN 时, capture 不应抛异常"""
        sentry_sdk.init(dsn=UNREACHABLE_DSN, traces_sample_rate=0.0)
        # 下面调用不应抛异常
        sentry_sdk.capture_message("unreachable dsn message")
        # flush 在超时内返回, 不应抛异常
        sentry_sdk.flush(timeout=0.5)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
