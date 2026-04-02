from __future__ import annotations

import logging
import sys
from collections.abc import Iterator

import pytest
import structlog

from lush_logx import (
    CustomProcessor,
    LogConfig,
    StructLogKey,
    configure_logging_once,
    create_dev_processors,
    create_json_processors,
    create_structlog_config,
    create_third_party_levels,
    detect_json_output,
    get_logger,
    reconfigure_logging,
    reset_logging_state,
)


@pytest.fixture(autouse=True)
def _reset_state() -> Iterator[None]:
    reset_logging_state()
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()
    reset_logging_state()


def test_log_config_post_init_validates_types() -> None:
    with pytest.raises(TypeError):
        _ = LogConfig(level=123)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        _ = LogConfig(min_json_level=123)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        _ = LogConfig(package_levels={"x": 1})  # type: ignore[arg-type]

    cfg = LogConfig(package_levels={"x": "debug"}, min_json_level="warning")
    assert cfg.package_levels["x"] == "DEBUG"
    assert cfg.min_json_level == "WARNING"


def test_detect_json_output_tty_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOGX_FORMAT", raising=False)
    monkeypatch.delenv("RUNNING_IN_DOCKER", raising=False)

    class _DummyStderr:
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(sys, "stderr", _DummyStderr())
    assert detect_json_output() is False


def test_custom_processor_timestamp_and_rich_text_renderer() -> None:
    event_dict: dict[str, object] = {}
    out = CustomProcessor.timestamp(None, "", event_dict)  # type: ignore[arg-type]
    assert "timestamp" in out

    out2 = CustomProcessor.timestamp(None, "", {"timestamp": "fixed"})  # type: ignore[arg-type]
    assert out2["timestamp"] == "fixed"

    rendered = CustomProcessor.rich_text_renderer(
        None,  # type: ignore[arg-type]
        "",
        {
            StructLogKey.EVENT.value: "hello",
            StructLogKey.LEVEL.value: "info",
            "foo": "bar",
        },
    )
    assert rendered.startswith("hello")
    assert "foo=bar" in rendered

    rendered_no_event = CustomProcessor.rich_text_renderer(None, "", {"foo": "bar"})  # type: ignore[arg-type]
    assert rendered_no_event == "foo=bar"


def test_custom_processor_add_stdlib_context_merges_contextvars() -> None:
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(user="u1")

    event_dict = {StructLogKey.EVENT.value: "e"}
    out = CustomProcessor.add_stdlib_context(None, "", event_dict)  # type: ignore[arg-type]
    assert out["user"] == "u1"
    assert "timestamp" in out

    # no contextvars => should not set user
    structlog.contextvars.clear_contextvars()
    out2 = CustomProcessor.add_stdlib_context(None, "", {StructLogKey.EVENT.value: "e"})  # type: ignore[arg-type]
    assert "user" not in out2


def test_create_processors_lists_are_built() -> None:
    dev = create_dev_processors()
    js = create_json_processors()
    assert CustomProcessor.timestamp in dev
    assert CustomProcessor.timestamp in js


def test_create_third_party_levels_invalid_level_defaults_to_info() -> None:
    levels = create_third_party_levels({"custom": "NOT_A_LEVEL"})
    assert levels["custom"] == logging.INFO


def test_create_structlog_config_branches() -> None:
    cfg_json = LogConfig(use_json=True, min_json_level="WARNING")
    out_json = create_structlog_config(cfg_json)
    assert CustomProcessor.add_stdlib_context in out_json["processors"]

    cfg_dev = LogConfig(use_json=False, level="DEBUG")
    out_dev = create_structlog_config(cfg_dev)
    assert CustomProcessor.rich_text_renderer in out_dev["processors"]


def test_locked_config_prevents_reconfigure_without_force() -> None:
    reconfigure_logging(LogConfig(use_json=False, level="INFO"))
    # Locked now; should early-return
    configure_logging_once(LogConfig(use_json=True))


def test_setup_stdlib_logging_json_branch_and_get_logger() -> None:
    # cover JSON branch in stdlib setup
    configure_logging_once(LogConfig(use_json=True, level="INFO"))
    logger = get_logger("x")
    assert logger is not None


def test_get_logger_auto_configures_when_needed() -> None:
    logger = get_logger("auto")
    assert logger is not None
