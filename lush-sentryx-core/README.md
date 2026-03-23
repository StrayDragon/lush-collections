# lush-sentryx-core

只做一件事: 对数据做脱敏/过滤.

它不依赖 `sentry-sdk`. 你可以把它接到 Sentry 的 `before_send` 上,也可以单独用在日志/审计/任务系统里.

## 例子

```python
from lush_sentryx_core import SENTRY_DEFAULT_DENYLIST, deep_scrub_sensitive_data

data = {"password": "secret", "profile": {"token": "xxx", "name": "demo"}}
deep_scrub_sensitive_data(data, SENTRY_DEFAULT_DENYLIST)
```

## 开发

```bash
uv sync -p 3.10 --frozen
uv run -p 3.10 pytest
```
