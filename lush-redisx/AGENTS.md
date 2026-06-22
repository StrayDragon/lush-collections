# lush-redisx — 子模块约定

> Async Redis manager and FastAPI integrations (mutex/idempotency/rate-limit).

## API 命名约定

- **节流 (throttle)** 为正确术语，公共 API 使用 `ThrottleResult`、`throttle_check_and_set`、`throttle_get_remaining`、`throttle_action`。
- `DebounceResult` 保留为 `ThrottleResult` 的向后兼容别名。
- `debounce_check_and_set`、`debounce_get_remaining`、`debounce_action` 保留为委托方法（deprecated），指向对应的 throttle 版本。

## 缓存策略

- `AsyncRedisManager` 和 `AsyncRedisPrefixedOp` 提供实例级 `default_null_value_strategy`，用于 `cache_get_or_set` 和 `async_cached_with` 的默认 null 值处理策略。
- 单次调用可通过 `null_value_strategy` 参数覆盖。

## Changelog

- **每次 minor/major (破坏性) 发布** 须在 `CHANGELOG.md` 中记录破坏性变更和重要变更.
- 记录内容: 破坏性变更 (Breaking Changes) + 重要变更 (Changes).
- 非破坏性修复 (patch) 不记录.

## 测试 & 覆盖率

- 100% branch coverage, `--cov-fail-under=100`.
