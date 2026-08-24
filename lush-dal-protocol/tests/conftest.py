"""hypothesis 属性测试的全局配置 (docs/design/11 §4).

CI 环境固定 seed 保证可复现; 本地默认随机探索.
"""

from __future__ import annotations

import os

if os.getenv("CI"):
    from hypothesis import settings

    settings.register_profile("ci", derandomize=True)
    settings.load_profile("ci")
