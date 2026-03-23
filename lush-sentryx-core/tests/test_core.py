"""lush-sentryx-core 核心功能测试"""


class TestDeepScrubSensitiveData:
    """测试深度递归清理敏感数据"""

    def test_basic_scrub(self):
        """测试基本的敏感数据清理"""
        from lush_sentryx_core.sdk.v2 import deep_scrub_sensitive_data

        data = {
            "password": "secret123",
            "config": {
                "api_token": "xxx",
                "name": "test",
                "nested": {
                    "secret_key": "hidden",
                },
            },
            "normal": "value",
        }

        sensitive_fields = {"password", "token", "secret"}
        deep_scrub_sensitive_data(data, sensitive_fields)

        assert data["password"] == "[Filtered]"
        assert data["config"]["api_token"] == "[Filtered]"
        assert data["config"]["nested"]["secret_key"] == "[Filtered]"
        assert data["config"]["name"] == "test"
        assert data["normal"] == "value"

    def test_with_list(self):
        """测试列表中的敏感数据清理"""
        from lush_sentryx_core.sdk.v2 import deep_scrub_sensitive_data

        data = {
            "users": [
                {"name": "user1", "password": "pass1"},
                {"name": "user2", "password": "pass2"},
            ]
        }

        sensitive_fields = {"password"}
        deep_scrub_sensitive_data(data, sensitive_fields)

        assert data["users"][0]["password"] == "[Filtered]"
        assert data["users"][1]["password"] == "[Filtered]"
        assert data["users"][0]["name"] == "user1"

    def test_max_depth_stop(self):
        """测试达到最大深度时不再继续清理"""
        from lush_sentryx_core.sdk.v2 import deep_scrub_sensitive_data

        data = {"level1": {"password": "secret"}}
        deep_scrub_sensitive_data(data, {"password"}, max_depth=0)

        assert data["level1"]["password"] == "secret"


class TestMaskEmail:
    """测试邮箱脱敏功能"""

    def test_mask_email_partially(self):
        """测试邮箱部分脱敏"""
        from lush_sentryx_core.sdk.v2 import mask_email_partially

        assert mask_email_partially("user@example.com") == "use***@example.com"
        assert mask_email_partially("ab@example.com") == "***@example.com"
        assert mask_email_partially("invalid-email") == "invalid-email"
        assert mask_email_partially("longusername@domain.com") == "lon***@domain.com"

    def test_mask_user_email_partially(self):
        """测试用户字典中邮箱脱敏"""
        from lush_sentryx_core.sdk.v2 import mask_user_email_partially

        user = {"email": "user@example.com", "name": "John"}
        mask_user_email_partially(user)
        assert user["email"] == "use***@example.com"
        assert user["name"] == "John"

        # 测试 mail 字段
        user2 = {"mail": "another@test.com"}
        mask_user_email_partially(user2)
        assert user2["mail"] == "ano***@test.com"


class TestCustomRepr:
    """测试自定义变量序列化"""

    def test_basic_types(self):
        """测试基本类型序列化"""
        from lush_sentryx_core.sdk.v2 import custom_repr

        assert custom_repr(True) == "True"
        assert custom_repr(False) == "False"
        assert custom_repr(123) == "123"
        assert custom_repr(3.14) == "3.14"
        assert custom_repr("hello") == "hello"
        assert custom_repr(None) == "None"

    def test_complex_types_return_none(self):
        """测试复杂类型返回 None"""
        from lush_sentryx_core.sdk.v2 import custom_repr

        assert custom_repr([1, 2]) is None
        assert custom_repr({"a": 1}) is None
        assert custom_repr((1, 2)) is None
        assert custom_repr({1, 2}) is None


class TestMaskStringPartially:
    """测试字符串部分脱敏"""

    def test_basic(self):
        """测试基本脱敏"""
        from lush_sentryx_core.sdk.v2 import mask_string_partially

        assert mask_string_partially("1234567890", visible_prefix=3, visible_suffix=2) == "123*****90"
        assert mask_string_partially("abc", visible_prefix=3) == "***"
        assert mask_string_partially("secret", visible_prefix=2, visible_suffix=1) == "se***t"


class TestParameterizeRequestUrls:
    """测试请求 URL 敏感参数清理"""

    def test_with_sensitive_params(self):
        """测试包含敏感参数的 URL"""
        from lush_sentryx_core.sdk.v2 import parameterize_request_urls

        request = {
            "url": "https://api.example.com/users?token=secret123",
            "query_string": "token=secret123",
        }
        parameterize_request_urls(request)
        assert request["url"] == "https://api.example.com/users"
        assert "query_string" not in request

    def test_without_sensitive_params(self):
        """测试不包含敏感参数的 URL"""
        from lush_sentryx_core.sdk.v2 import parameterize_request_urls

        request = {"url": "https://api.example.com/users?page=1"}
        parameterize_request_urls(request)
        assert request["url"] == "https://api.example.com/users?page=1"


class TestScrubDictKeys:
    """测试字典顶层敏感字段清理"""

    def test_basic(self):
        """测试基本清理"""
        from lush_sentryx_core.sdk.v2 import scrub_dict_keys

        data = {"password": "secret", "username": "john", "api_key": "xxx"}
        result = scrub_dict_keys(data, {"password", "key"})

        assert result["password"] == "[Filtered]"
        assert result["api_key"] == "[Filtered]"
        assert result["username"] == "john"


class TestScrubStacktraceVars:
    """测试堆栈帧中局部变量清理"""

    def test_scrub_stacktrace_vars_exception_and_threads(self):
        """测试异常与线程堆栈中的嵌套敏感字段清理"""
        from lush_sentryx_core.sdk.v2 import scrub_stacktrace_vars

        event = {
            "exception": {
                "values": [
                    {
                        "stacktrace": {
                            "frames": [
                                {
                                    "vars": {
                                        "config": {"password": "secret", "safe": "ok"},
                                        "list": [{"token": "value"}],
                                        "scalar": "keep",
                                    }
                                }
                            ]
                        }
                    }
                ]
            },
            "threads": {
                "values": [
                    {
                        "stacktrace": {
                            "frames": [
                                {
                                    "vars": {
                                        "nested": {"api_key": "aaa", "plain": "ok"},
                                        "list": [{"secret": "bbb"}],
                                    }
                                }
                            ]
                        }
                    }
                ]
            },
        }

        scrub_stacktrace_vars(event, {"password", "token", "secret", "api_key"})

        exception_vars = event["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]  # pyright: ignore[reportTypedDictNotRequiredAccess]
        assert exception_vars["config"]["password"] == "[Filtered]"
        assert exception_vars["config"]["safe"] == "ok"
        assert exception_vars["list"][0]["token"] == "[Filtered]"
        assert exception_vars["scalar"] == "keep"

        thread_vars = event["threads"]["values"][0]["stacktrace"]["frames"][0]["vars"]  # pyright: ignore[reportTypedDictNotRequiredAccess]
        assert thread_vars["nested"]["api_key"] == "[Filtered]"
        assert thread_vars["nested"]["plain"] == "ok"
        assert thread_vars["list"][0]["secret"] == "[Filtered]"


class TestFilters:
    """测试过滤器"""

    def test_create_additional_filter(self):
        """测试额外过滤器创建"""
        from lush_sentryx_core.sdk.v2 import create_additional_filter

        filter_func = create_additional_filter({"password", "token"})

        event = {
            "user": {"email": "user@example.com"},
            "extra": {"password": "secret"},
            "contexts": {"config": {"token": "xxx"}},
        }

        result = filter_func(event, None)

        assert result is not None
        assert result["user"]["email"] == "use***@example.com"  # pyright: ignore[reportTypedDictNotRequiredAccess]
        assert result["extra"]["password"] == "[Filtered]"  # pyright: ignore[reportTypedDictNotRequiredAccess]
        assert result["contexts"]["config"]["token"] == "[Filtered]"  # pyright: ignore[reportTypedDictNotRequiredAccess]

    def test_create_additional_filter_request_and_stacktrace(self):
        """测试请求参数清理与堆栈变量清理"""
        from lush_sentryx_core.sdk.v2 import create_additional_filter

        filter_func = create_additional_filter({"token"})

        event = {
            "request": {"url": "https://api.example.com/users?token=secret123", "query_string": "token=secret123"},
            "user": {"email": "person@example.com"},
            "exception": {
                "values": [
                    {
                        "stacktrace": {
                            "frames": [
                                {"vars": {"payload": {"token": "secret123", "safe": "ok"}}},
                            ]
                        }
                    }
                ]
            },
        }

        result = filter_func(event, None)

        assert result is not None
        assert result["request"]["url"] == "https://api.example.com/users"  # pyright: ignore[reportTypedDictNotRequiredAccess]
        assert "query_string" not in result["request"]  # pyright: ignore[reportTypedDictNotRequiredAccess]
        assert result["user"]["email"] == "per***@example.com"  # pyright: ignore[reportTypedDictNotRequiredAccess]
        assert result["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]["payload"]["token"] == "[Filtered]"  # pyright: ignore[reportTypedDictNotRequiredAccess]
        assert result["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]["payload"]["safe"] == "ok"  # pyright: ignore[reportTypedDictNotRequiredAccess]

    def test_create_additional_filter_returns_none_on_error(self):
        """测试异常场景返回 None"""
        from lush_sentryx_core.sdk.v2 import create_additional_filter

        filter_func = create_additional_filter({"token"})
        assert filter_func(None, None) is None

    def test_create_transaction_filter(self):
        """测试事务名称过滤器"""
        from lush_sentryx_core.sdk.v2 import create_transaction_filter

        filter_func = create_transaction_filter()

        event = {"transaction": "/api/users?token=secret123"}
        result = filter_func(event, None)

        assert result is not None
        assert "secret123" not in result["transaction"]  # pyright: ignore[reportTypedDictNotRequiredAccess]

    def test_create_transaction_filter_handles_invalid_event(self):
        """测试异常输入不影响流程"""
        from lush_sentryx_core.sdk.v2 import create_transaction_filter

        filter_func = create_transaction_filter()
        assert filter_func(None, None) is None


class TestConstants:
    """测试常量"""

    def test_constants_available(self):
        """测试常量可用性"""
        from lush_sentryx_core.sdk.v2 import (
            BUSINESS_SENSITIVE_FIELDS,
            FILTERED_PLACEHOLDER,
            SENSITIVE_URL_PATTERNS,
            SENTRY_DEFAULT_DENYLIST,
        )

        assert isinstance(SENTRY_DEFAULT_DENYLIST, frozenset)
        assert "password" in SENTRY_DEFAULT_DENYLIST
        assert "token" in SENTRY_DEFAULT_DENYLIST

        assert isinstance(BUSINESS_SENSITIVE_FIELDS, frozenset)
        assert FILTERED_PLACEHOLDER == "[Filtered]"
        assert len(SENSITIVE_URL_PATTERNS) > 0


class TestTypes:
    """测试类型定义"""

    def test_types_available(self):
        """测试类型可导入"""
        from lush_sentryx_core.sdk.v2.types import (
            Breadcrumb,
            Event,
            ExcInfo,
            Hint,
            SensitiveFields,
        )

        # 类型别名应该可以用于注解
        def example_filter(event: Event, hint: Hint) -> Event | None:
            return event

        # 验证类型存在
        assert Event is not None
        assert Hint is not None
        assert Breadcrumb is not None
        assert ExcInfo is not None
        assert SensitiveFields is not None


class TestBackwardCompatibility:
    """测试向后兼容性 - 直接从 lush_sentryx_core 导入"""

    def test_direct_import(self):
        """测试直接从 lush_sentryx_core 导入"""
        from lush_sentryx_core import (
            SENTRY_DEFAULT_DENYLIST,
            create_additional_filter,
            deep_scrub_sensitive_data,
            mask_email_partially,
        )

        assert "password" in SENTRY_DEFAULT_DENYLIST
        assert callable(create_additional_filter)
        assert callable(deep_scrub_sensitive_data)
        assert callable(mask_email_partially)

    def test_sdk_namespace_import(self):
        """测试通过 sdk.v2 命名空间导入"""
        from lush_sentryx_core.sdk.v2 import (
            SENTRY_DEFAULT_DENYLIST,
            Event,
            Hint,
            create_additional_filter,
        )

        assert "password" in SENTRY_DEFAULT_DENYLIST
        assert callable(create_additional_filter)
        assert Event is not None
        assert Hint is not None

    def test_sdk_module_access(self):
        """测试通过 sdk 模块访问"""
        from lush_sentryx_core import sdk

        assert hasattr(sdk, "v2")
        assert hasattr(sdk.v2, "SENTRY_DEFAULT_DENYLIST")
        assert hasattr(sdk.v2, "create_additional_filter")
