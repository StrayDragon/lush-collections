# Changelog

本文件记录 `lush-sentryx-core` 的破坏性变更和重要变更，帮助从低版本升级。

## 0.2.0

### Breaking Changes

**删除 `BUSINESS_SENSITIVE_FIELDS` 常量**

`BUSINESS_SENSITIVE_FIELDS` 是一个空的 `frozenset`，设计用于存放业务敏感字段。现已删除，改为通过 `create_enhanced_scrubber(denylist=...)` 直接传入业务字段。

```python
# 旧方式 (已删除)
from lush_sentryx_core import BUSINESS_SENSITIVE_FIELDS

# 新方式
from lush_sentryx_core import create_additional_filter, SENTRY_DEFAULT_DENYLIST

business_fields = {"custom_secret", "internal_token", "api_key"}
filter_fn = create_additional_filter(SENTRY_DEFAULT_DENYLIST | business_fields)
```
