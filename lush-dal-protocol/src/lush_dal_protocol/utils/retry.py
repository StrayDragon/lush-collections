"""通用重试配置."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class RetryConfig:
    """重试策略配置.

    支持指数退避 + 可选抖动.
    """

    max_attempts: int = 3
    initial_delay: float = 0.1
    max_delay: float = 2.0
    exponential_base: float = 2.0
    jitter: bool = True

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts 必须>=1, 当前值: {self.max_attempts}")
        if self.initial_delay < 0:
            raise ValueError(f"initial_delay 必须>=0, 当前值: {self.initial_delay}")
        if self.max_delay < self.initial_delay:
            raise ValueError(f"max_delay({self.max_delay}) 必须>=initial_delay({self.initial_delay})")
        if self.exponential_base <= 1:
            raise ValueError(f"exponential_base 必须>1, 当前值: {self.exponential_base}")

    def calculate_delay(self, attempt: int) -> float:
        """根据当前重试次数计算等待时间 (秒)."""
        if attempt <= 0:
            return 0.0

        delay = self.initial_delay * (self.exponential_base ** (attempt - 1))
        delay = min(delay, self.max_delay)

        if self.jitter and delay > 0:
            jitter_range = delay * 0.2
            delay = delay + random.uniform(-jitter_range, jitter_range)  # noqa: S311
            delay = max(0, min(delay, self.max_delay))

        return delay


DEFAULT_RETRY_CONFIG = RetryConfig(max_attempts=3, initial_delay=0.1, max_delay=1.0)
