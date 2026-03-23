# lush-sentryx

围绕 `sentry-sdk` 做的一层轻量封装: 把配置聚在一起,默认做脱敏,同时把“初始化失败”当成可降级事件处理.

如果你只想要脱敏/过滤能力,不依赖 sentry-sdk,看 `lush-sentryx-core`.

## 安装

按框架装 extra 会更省事:

- `fastapi`: `lush-sentryx[fastapi]`
- `flask`: `lush-sentryx[flask]`
- `django`: `lush-sentryx[django]`

## 快速开始

```python
from lush_sentryx import SentryConfig
from lush_sentryx.integrations.common import default_common_integrations

config = SentryConfig(
    dsn="https://xxx@sentry.io/123",
    enabled=True,
    integrations=[*default_common_integrations()],
)
manager = config.create_manager()
manager.init()
```

## 开发

```bash
uv sync -p 3.10 --frozen
uv run -p 3.10 pytest
```
