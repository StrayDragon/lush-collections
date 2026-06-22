# Changelog

本文件记录 `lush-sentryx` 的破坏性变更和重要变更，帮助从低版本升级。

## 0.3.0

### Breaking Changes

**删除 `scrub_business_sensitive_fields` 配置参数**

`sentryx_init()` 中的 `scrub_business_sensitive_fields` 参数已删除。现在通过 `create_enhanced_scrubber(denylist=...)` 直接传入业务敏感字段。

```python
# 旧方式 (已删除)
import lush_sentryx
lush_sentryx.sentryx_init(
    dsn="...",
    scrub_business_sensitive_fields=True,  # 已删除
)

# 新方式
from lush_sentryx import create_enhanced_scrubber
import sentry_sdk

scrubber = create_enhanced_scrubber(
    denylist={"custom_secret", "internal_token", "api_key"}
)
sentry_sdk.init(dsn="...", event_scrubber=scrubber)
```

### Changes

- 依赖升级: `lush-sentryx-core>=0.2.0`
