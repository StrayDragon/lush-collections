"""retry 模块测试."""

import pytest

from lush_dalx.retry import DEFAULT_RETRY_CONFIG, RetryConfig


class TestRetryConfig:
    def test_defaults(self):
        cfg = RetryConfig()
        assert cfg.max_attempts == 3
        assert cfg.initial_delay == 0.1
        assert cfg.max_delay == 2.0
        assert cfg.exponential_base == 2.0
        assert cfg.jitter is True

    def test_invalid_max_attempts(self):
        with pytest.raises(ValueError, match="max_attempts"):
            RetryConfig(max_attempts=0)

    def test_invalid_initial_delay(self):
        with pytest.raises(ValueError, match="initial_delay"):
            RetryConfig(initial_delay=-1)

    def test_invalid_max_delay(self):
        with pytest.raises(ValueError, match="max_delay"):
            RetryConfig(max_delay=0.01, initial_delay=0.1)

    def test_invalid_exponential_base(self):
        with pytest.raises(ValueError, match="exponential_base"):
            RetryConfig(exponential_base=1)

    def test_calculate_delay_zero_attempt(self):
        cfg = RetryConfig(jitter=False)
        assert cfg.calculate_delay(0) == 0.0

    def test_calculate_delay_no_jitter(self):
        cfg = RetryConfig(initial_delay=0.1, exponential_base=2.0, max_delay=10.0, jitter=False)
        assert cfg.calculate_delay(1) == pytest.approx(0.1)
        assert cfg.calculate_delay(2) == pytest.approx(0.2)
        assert cfg.calculate_delay(3) == pytest.approx(0.4)

    def test_calculate_delay_capped(self):
        cfg = RetryConfig(initial_delay=1.0, exponential_base=10.0, max_delay=5.0, jitter=False)
        assert cfg.calculate_delay(3) == pytest.approx(5.0)

    def test_calculate_delay_with_jitter(self):
        cfg = RetryConfig(initial_delay=1.0, max_delay=10.0, jitter=True)
        delay = cfg.calculate_delay(1)
        assert 0.8 <= delay <= 1.2

    def test_calculate_delay_jitter_capped_to_max(self):
        cfg = RetryConfig(initial_delay=1.0, exponential_base=10.0, max_delay=5.0, jitter=True)
        for _ in range(50):
            delay = cfg.calculate_delay(3)
            assert 0 <= delay <= 5.0


class TestDefaultRetryConfig:
    def test_default_config(self):
        assert DEFAULT_RETRY_CONFIG.max_attempts == 3
        assert DEFAULT_RETRY_CONFIG.initial_delay == 0.1
        assert DEFAULT_RETRY_CONFIG.max_delay == 1.0
