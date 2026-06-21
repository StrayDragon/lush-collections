from __future__ import annotations

import logging
import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lush_sentryx import SentryConfig, SentryManager, core
from lush_sentryx.integrations import django as django_integration
from lush_sentryx.integrations import extras as extras_integration
from lush_sentryx.integrations import fastapi as fastapi_integration
from lush_sentryx.integrations import flask as flask_integration
from lush_sentryx.scrubbers import create_enhanced_scrubber, get_all_sensitive_fields


def _install_dummy_integration_module(monkeypatch: pytest.MonkeyPatch, module_name: str, **attrs) -> None:
    mod = types.ModuleType(module_name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    monkeypatch.setitem(sys.modules, module_name, mod)


def test_scrubbers_branches(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    # 正常调用,传入自定义 denylist
    scrubber = create_enhanced_scrubber(denylist={"custom_secret"})
    assert scrubber is not None

    class _BoomScrubber:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            if kwargs:
                raise RuntimeError("boom")

    monkeypatch.setattr("lush_sentryx.scrubbers.EventScrubber", _BoomScrubber)
    scrubber = create_enhanced_scrubber()
    assert isinstance(scrubber, _BoomScrubber)
    assert any("创建EventScrubber失败" in r.message for r in caplog.records)

    fields = get_all_sensitive_fields(additional_denylist={"x"})
    assert "x" in fields


def test_scrubbers_get_all_sensitive_fields_default_branches() -> None:
    fields = get_all_sensitive_fields(additional_denylist=None)
    assert isinstance(fields, set)
    # 传入额外的 denylist
    fields2 = get_all_sensitive_fields(additional_denylist={"extra_field"})
    assert "extra_field" in fields2


def test_extras_default_integrations_importerror_and_success(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force ImportError path by providing module without the expected symbol.
    _install_dummy_integration_module(monkeypatch, "sentry_sdk.integrations.sqlalchemy")
    assert extras_integration.default_sqlalchemy_integration() is None

    class _SqlalchemyIntegration:
        def __init__(self, **kwargs):  # noqa: ANN003
            self.kwargs = kwargs

    _install_dummy_integration_module(monkeypatch, "sentry_sdk.integrations.sqlalchemy", SqlalchemyIntegration=_SqlalchemyIntegration)
    assert extras_integration.default_sqlalchemy_integration() is not None
    assert extras_integration.default_sqlalchemy_integration({"x": 1}) is not None  # type: ignore[arg-type]

    _install_dummy_integration_module(monkeypatch, "sentry_sdk.integrations.redis")
    assert extras_integration.default_redis_integration() is None

    class _RedisIntegration:
        def __init__(self, **kwargs):  # noqa: ANN003
            self.kwargs = kwargs

    _install_dummy_integration_module(monkeypatch, "sentry_sdk.integrations.redis", RedisIntegration=_RedisIntegration)
    assert extras_integration.default_redis_integration({"max_data_size": 2048}) is not None
    assert extras_integration.default_redis_integration({}) is not None

    _install_dummy_integration_module(monkeypatch, "sentry_sdk.integrations.logging")
    assert extras_integration.default_logging_integration() is None

    class _LoggingIntegration:
        def __init__(self, **kwargs):  # noqa: ANN003
            self.kwargs = kwargs

    _install_dummy_integration_module(monkeypatch, "sentry_sdk.integrations.logging", LoggingIntegration=_LoggingIntegration)
    assert extras_integration.default_logging_integration({"level": logging.INFO, "event_level": logging.ERROR}) is not None
    assert extras_integration.default_logging_integration({}) is not None

    ints = extras_integration.default_common_integrations(
        enable_sqlalchemy=True,
        enable_redis=True,
        enable_logging=True,
        logging_level=logging.INFO,
        logging_event_level=logging.CRITICAL,
        redis_options={"max_data_size": 1},
    )
    assert len(ints) == 3

    _install_dummy_integration_module(monkeypatch, "sentry_sdk.integrations.sqlalchemy")
    ints2 = extras_integration.default_common_integrations(enable_sqlalchemy=True, enable_redis=False, enable_logging=False)
    assert ints2 == []

    _install_dummy_integration_module(monkeypatch, "sentry_sdk.integrations.redis")
    ints2b = extras_integration.default_common_integrations(enable_sqlalchemy=False, enable_redis=True, enable_logging=False)
    assert ints2b == []

    _install_dummy_integration_module(monkeypatch, "sentry_sdk.integrations.logging", LoggingIntegration=_LoggingIntegration)
    ints3 = extras_integration.default_common_integrations(enable_sqlalchemy=False, enable_redis=False, enable_logging=True)
    assert len(ints3) == 1

    _install_dummy_integration_module(monkeypatch, "sentry_sdk.integrations.logging")
    ints4 = extras_integration.default_common_integrations(enable_sqlalchemy=False, enable_redis=False, enable_logging=True)
    assert ints4 == []

    _install_dummy_integration_module(monkeypatch, "sentry_sdk.integrations.logging", LoggingIntegration=_LoggingIntegration)
    ints5 = extras_integration.default_common_integrations(
        enable_sqlalchemy=False,
        enable_redis=False,
        enable_logging=True,
        logging_level=logging.DEBUG,
        logging_event_level=None,
    )
    assert len(ints5) == 1

    ints6 = extras_integration.default_common_integrations(enable_sqlalchemy=False, enable_redis=False, enable_logging=False)
    assert ints6 == []


def test_framework_integrations_factories(monkeypatch: pytest.MonkeyPatch) -> None:
    # --- FastAPI: ImportError branches
    _install_dummy_integration_module(monkeypatch, "sentry_sdk.integrations.fastapi")
    _install_dummy_integration_module(monkeypatch, "sentry_sdk.integrations.starlette")
    cfg = fastapi_integration.FastAPISentryConfig(dsn="x", enabled=True, enable_sqlalchemy=False)
    with pytest.raises(ImportError):
        _ = cfg.collect_integrations()

    with pytest.raises(ImportError):
        _ = fastapi_integration.default_fastapi_integrations()

    # --- FastAPI: success branches
    class _FastApiIntegration:
        def __init__(self, **kwargs):  # noqa: ANN003
            self.kwargs = kwargs

    class _StarletteIntegration:
        def __init__(self, **kwargs):  # noqa: ANN003
            self.kwargs = kwargs

    _install_dummy_integration_module(monkeypatch, "sentry_sdk.integrations.fastapi", FastApiIntegration=_FastApiIntegration)
    _install_dummy_integration_module(monkeypatch, "sentry_sdk.integrations.starlette", StarletteIntegration=_StarletteIntegration)

    cfg2 = fastapi_integration.FastAPISentryConfig(
        dsn="x",
        enabled=True,
        failed_request_status_codes={500},
        enable_sqlalchemy=True,
        sqlalchemy_integration_factory=object,
    )
    integrations = cfg2.collect_integrations()
    assert any(isinstance(i, _FastApiIntegration) for i in integrations)
    assert any(isinstance(i, _StarletteIntegration) for i in integrations)

    _ = fastapi_integration.default_fastapi_integrations({"transaction_style": "endpoint"})
    _ = fastapi_integration.default_fastapi_integrations()

    cfg3 = fastapi_integration.FastAPISentryConfig(dsn="x", enabled=True, failed_request_status_codes=None, enable_sqlalchemy=False)
    _ = cfg3.collect_integrations()

    def _boom_sqlalchemy() -> object:
        raise ImportError("boom")

    cfg4 = fastapi_integration.FastAPISentryConfig(
        dsn="x",
        enabled=True,
        failed_request_status_codes=None,
        enable_sqlalchemy=True,
        sqlalchemy_integration_factory=_boom_sqlalchemy,  # type: ignore[arg-type]
    )
    _ = cfg4.collect_integrations()

    # set_sentry_context_from_request
    fake_manager = SimpleNamespace(
        set_tag=Mock(),
        set_user_context=Mock(),
        logger=logging.getLogger("t"),
    )
    fake_request = SimpleNamespace(method="GET", url=SimpleNamespace(path="/p"))
    fastapi_integration.set_sentry_context_from_request(fake_manager, fake_request, RuntimeError("x"))  # type: ignore[arg-type]

    # user/context branches
    fastapi_integration.set_sentry_context_from_request(
        fake_manager,
        fake_request,
        RuntimeError("x"),
        get_user_id=lambda _r: "u",
        get_client_ip=lambda _r: "127.0.0.1",
    )
    fastapi_integration.set_sentry_context_from_request(
        fake_manager,
        fake_request,
        RuntimeError("x"),
        get_user_id=lambda _r: "",
        get_client_ip=lambda _r: None,
    )

    # error branch
    fake_manager.set_tag.side_effect = RuntimeError("boom")
    fastapi_integration.set_sentry_context_from_request(fake_manager, fake_request, RuntimeError("x"))  # type: ignore[arg-type]

    # --- Flask: ImportError + success
    _install_dummy_integration_module(monkeypatch, "sentry_sdk.integrations.flask")
    cfg_f = flask_integration.FlaskSentryConfig(dsn="x", enabled=True, enable_sqlalchemy=False)
    with pytest.raises(ImportError):
        _ = cfg_f.collect_integrations()

    with pytest.raises(ImportError):
        _ = flask_integration.default_flask_integration()

    class _FlaskIntegration:
        def __init__(self, **kwargs):  # noqa: ANN003
            self.kwargs = kwargs

    _install_dummy_integration_module(monkeypatch, "sentry_sdk.integrations.flask", FlaskIntegration=_FlaskIntegration)
    cfg_f2 = flask_integration.FlaskSentryConfig(dsn="x", enabled=True, enable_sqlalchemy=False)
    assert any(isinstance(i, _FlaskIntegration) for i in cfg_f2.collect_integrations())
    assert flask_integration.create_sentry_manager_for_flask(cfg_f2) is not None
    _ = flask_integration.default_flask_integration({"transaction_style": "url"})
    _ = flask_integration.default_flask_integration()

    def _boom_sqlalchemy2() -> object:
        raise ImportError("boom")

    cfg_f3 = flask_integration.FlaskSentryConfig(
        dsn="x",
        enabled=True,
        enable_sqlalchemy=True,
        sqlalchemy_integration_factory=_boom_sqlalchemy2,  # type: ignore[arg-type]
    )
    _ = cfg_f3.collect_integrations()

    # --- Django: default integration + config collect + create manager
    class _DjangoIntegration:
        def __init__(self, **kwargs):  # noqa: ANN003
            self.kwargs = kwargs

    _install_dummy_integration_module(monkeypatch, "sentry_sdk.integrations.django", DjangoIntegration=_DjangoIntegration)
    _ = django_integration.default_django_integration({"middleware_spans": True})
    _ = django_integration.default_django_integration()
    cfg_d = django_integration.DjangoSentryConfig(dsn="x", enabled=True)
    assert any(isinstance(i, _DjangoIntegration) for i in cfg_d.collect_integrations())
    assert django_integration.create_sentry_manager_for_django(cfg_d) is not None


def test_core_default_integration_factories(monkeypatch: pytest.MonkeyPatch) -> None:
    class _SqlalchemyIntegration:
        pass

    _install_dummy_integration_module(monkeypatch, "sentry_sdk.integrations.sqlalchemy", SqlalchemyIntegration=_SqlalchemyIntegration)
    assert isinstance(core.default_sqlalchemy_integration(), _SqlalchemyIntegration)

    class _RedisIntegration:
        pass

    _install_dummy_integration_module(monkeypatch, "sentry_sdk.integrations.redis", RedisIntegration=_RedisIntegration)

    import importlib

    monkeypatch.setattr(importlib, "import_module", lambda name: object() if name == "redis" else importlib.import_module(name))
    assert isinstance(core.default_redis_integration(), _RedisIntegration)


def test_sentry_config_collect_integrations_and_init(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy_int = object()  # type: ignore[var-annotated]

    cfg = SentryConfig(
        dsn="dsn",
        enabled=True,
        redis_integration=None,
        logging_integration=lambda: dummy_int,  # type: ignore[return-value]
        integrations=[dummy_int],  # type: ignore[list-item]
    )
    ints = cfg.collect_integrations()
    assert ints.count(dummy_int) >= 2

    def _boom_logging() -> object:
        raise ImportError("boom")

    cfg2 = SentryConfig(dsn="dsn", enabled=True, redis_integration=None, logging_integration=_boom_logging)  # type: ignore[arg-type]
    assert cfg2.collect_integrations() == []

    # init() should call sentry_sdk.init and set_tag.
    init_mock = Mock()
    set_tag_mock = Mock()
    monkeypatch.setattr(core.sentry_sdk, "init", init_mock)
    monkeypatch.setattr(core.sentry_sdk, "set_tag", set_tag_mock)
    assert cfg.init() is True
    assert init_mock.called
    assert set_tag_mock.called


def test_sentry_manager_init_tags_and_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = SentryConfig(dsn="dsn", enabled=True, service_name="")
    manager = SentryManager(cfg, logger=logging.getLogger("t"))

    # success path, service_name empty => skip service tag
    monkeypatch.setattr(core, "create_enhanced_scrubber", lambda **_kw: object())
    monkeypatch.setattr(core, "get_all_sensitive_fields", lambda **_kw: {"x"})
    monkeypatch.setattr(SentryConfig, "collect_integrations", lambda _self: [])
    monkeypatch.setattr(core.sentry_sdk, "init", lambda **_kw: None)

    set_tag_mock = Mock()
    monkeypatch.setattr(core.sentry_sdk, "set_tag", set_tag_mock)
    assert manager.init() is True
    assert all(call.args[0] != "service" for call in set_tag_mock.mock_calls)

    # tag setting failure should be swallowed
    monkeypatch.setattr(core.sentry_sdk, "set_tag", Mock(side_effect=RuntimeError("boom")))
    assert manager.init() is True

    # ImportError should be caught and return False
    monkeypatch.setattr(core, "create_enhanced_scrubber", Mock(side_effect=ImportError("boom")))
    assert manager.init() is False


def test_sentry_manager_capture_exception_and_message_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = SentryConfig(dsn="dsn", enabled=True)
    manager = SentryManager(cfg, logger=Mock())

    class _Scope:
        def __init__(self) -> None:
            self.level = None
            self.fingerprint = None
            self.trace_id = None

        def set_extra(self, k, v):  # noqa: ANN001
            pass

        def set_tag(self, k, v):  # noqa: ANN001
            pass

        def set_user(self, user):  # noqa: ANN001
            pass

        def set_trace_id(self, v):  # noqa: ANN001
            self.trace_id = v

    class _ScopeCtx:
        def __enter__(self):  # noqa: ANN204
            return _Scope()

        def __exit__(self, *args):  # noqa: ANN001, ANN204
            return False

    def _new_scope() -> _ScopeCtx:
        return _ScopeCtx()

    monkeypatch.setattr(core.sentry_sdk, "new_scope", _new_scope)
    monkeypatch.setattr(core.sentry_sdk, "capture_exception", Mock())
    manager.capture_exception(
        RuntimeError("x"),
        extras={"a": 1},
        tags={"t": "v"},
        user={"id": "u"},
        trace_id="tid",
        level="warning",
        fingerprint=["x"],
        unknown_key=1,
    )

    # exception path
    monkeypatch.setattr(core.sentry_sdk, "capture_exception", Mock(side_effect=RuntimeError("boom")))
    manager.capture_exception(RuntimeError("x"))
    assert manager.logger.exception.called

    monkeypatch.setattr(core.sentry_sdk, "capture_message", Mock(side_effect=RuntimeError("boom")))
    manager.capture_message(
        "m",
        level="debug",
        extras={"a": 1},
        tags={"t": "v"},
        user={"id": "u"},
        trace_id="tid",
        fingerprint=["x"],
        unknown_key=1,
    )
    assert manager.logger.debug.called


def test_sentry_manager_user_tag_breadcrumb_and_connection_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = SentryConfig(dsn="dsn", enabled=True)
    logger = Mock()
    manager = SentryManager(cfg, logger=logger)
    manager._initialized = True

    monkeypatch.setattr(core.sentry_sdk, "set_user", Mock())
    manager.set_user_context({"email": "a@b.com"})
    assert logger.warning.called

    monkeypatch.setattr(core.sentry_sdk, "set_tag", Mock(side_effect=RuntimeError("boom")))
    manager.set_tag("k", "v")
    assert logger.warning.called

    monkeypatch.setattr(core.sentry_sdk, "add_breadcrumb", Mock(side_effect=RuntimeError("boom")))
    manager.add_breadcrumb("m")
    assert logger.debug.called

    monkeypatch.setattr(core.sentry_sdk, "capture_message", Mock())

    monkeypatch.setattr(core.sentry_sdk, "flush", Mock(side_effect=TimeoutError()))
    assert manager.check_connection(timeout=0.01) is False

    monkeypatch.setattr(core.sentry_sdk, "flush", Mock(side_effect=RuntimeError("boom")))
    assert manager.check_connection(timeout=0.01) is False

    monkeypatch.setattr(core.sentry_sdk, "flush", Mock())
    assert manager.check_connection(timeout=0.01) is True
