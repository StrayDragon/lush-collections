"""BDD 步骤定义: lush-redisx 核心行为 (AsyncRedisPrefixedOp).

使用策略:
- 所有步骤为同步函数, 通过 nest_asyncio 在已运行的事件循环中执行异步方法
- bdd_context dict 用于步骤间状态传递
- Then 步骤使用裸 Redis 操作验证数据库状态, 不依赖被测 API
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import nest_asyncio
import pytest
from pytest_bdd import given, parsers, then, when

from lush_redisx import (
    AsyncRedisManager,
    AsyncRedisPrefixedOp,
    DebounceResult,
    RedisCacheAll,
    RedisSkipNone,
    RedisTTLNone,
    SerializationMode,
)

# 允许嵌套事件循环: pytest-asyncio 已运行 loop, 但 pytest-bdd 要求同步步骤
nest_asyncio.apply()


def _run(coro: Any) -> Any:
    """在同步步骤中运行异步协程 (复用 pytest-asyncio 事件循环)."""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


# ---------------------------------------------------------------------------
# bdd_context fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def bdd_context() -> dict[str, Any]:
    """BDD 步骤间共享状态."""
    return {}


# ---------------------------------------------------------------------------
# Raw Redis helpers for Then verification (bypass prefix)
# ---------------------------------------------------------------------------


def _raw_redis(redis_mgr: AsyncRedisManager) -> redis.asyncio.Redis:  # noqa: F821
    """获取底层 Redis 连接 (绕过 prefix)."""
    return redis_mgr.origin_redis_conn  # type: ignore[return-value]


async def _raw_get(redis_mgr: AsyncRedisManager, key: str) -> str | None:
    return await _raw_redis(redis_mgr).get(key)


async def _raw_ttl(redis_mgr: AsyncRedisManager, key: str) -> int:
    return await _raw_redis(redis_mgr).ttl(key)


async def _raw_exists(redis_mgr: AsyncRedisManager, key: str) -> bool:
    return bool(await _raw_redis(redis_mgr).exists(key))


async def _raw_delete(redis_mgr: AsyncRedisManager, key: str) -> None:
    await _raw_redis(redis_mgr).delete(key)


# ---------------------------------------------------------------------------
# Named JSON constants for feature file usage (Gherkin strips inner quotes)
# ---------------------------------------------------------------------------

_JSON_SAMPLES: dict[str, Any] = {
    "简单字典": {"a": 1, "b": 2},
    "单键值对": {"k": "v"},
    "小字典": {"x": 1},
}


# ---------------------------------------------------------------------------
# Given steps
# ---------------------------------------------------------------------------


@given(parsers.parse('已使用 prefixed 操作 "{key_prefix}"'))
def given_prefixed_op(key_prefix: str, bdd_context: dict[str, Any], redis_mgr: AsyncRedisManager) -> None:
    op = AsyncRedisPrefixedOp(redis_mgr.origin_redis_conn, key_prefix)  # type: ignore[arg-type]
    bdd_context["op"] = op
    bdd_context["key_prefix"] = key_prefix


@given(parsers.parse('Redis 键 "{raw_key}" 已存在且值为 "{value}"'))
def given_key_exists(raw_key: str, value: str, redis_mgr: AsyncRedisManager) -> None:
    _run(_raw_redis(redis_mgr).set(raw_key, value))


@given(parsers.parse('Redis 键 "{raw_key}" 已存在且值为 "{value}" 且过期时间为 "{ttl:d}" 秒'))
def given_key_with_ttl(raw_key: str, value: str, ttl: int, redis_mgr: AsyncRedisManager) -> None:
    _run(_raw_redis(redis_mgr).set(raw_key, value, ex=ttl))


@given(parsers.parse('Redis 键 "{raw_key}" 不存在'))
def given_key_not_exists(raw_key: str, redis_mgr: AsyncRedisManager) -> None:
    _run(_raw_delete(redis_mgr, raw_key))


# ---------------------------------------------------------------------------
# When steps: KV 操作
# ---------------------------------------------------------------------------


@when(parsers.parse('设置键 "{name}" 值为 "{value}"'))
def when_set(name: str, value: str, bdd_context: dict[str, Any]) -> None:
    bdd_context["last_result"] = _run(bdd_context["op"].set(name, value))


@when(parsers.parse('设置键 "{name}" 值为 "{value}" 且过期时间为 "{expire:d}" 秒'))
def when_set_with_ttl(name: str, value: str, expire: int, bdd_context: dict[str, Any]) -> None:
    bdd_context["last_result"] = _run(bdd_context["op"].set(name, value, expire=expire))


@when(parsers.parse('设置键 "{name}" JSON 值为 "{json_value}"'))
def when_set_json(name: str, json_value: str, bdd_context: dict[str, Any]) -> None:
    parsed = json.loads(json_value)
    bdd_context["last_result"] = _run(bdd_context["op"].set_json(name, parsed))


@when(parsers.parse('设置键 "{name}" JSON 值为 "{json_value}" 且过期时间为 "{expire:d}" 秒且 NX'))
def when_set_json_nx(name: str, json_value: str, expire: int, bdd_context: dict[str, Any]) -> None:
    parsed = json.loads(json_value)
    bdd_context["last_result"] = _run(bdd_context["op"].set_json(name, parsed, expire_seconds=expire, nx=True))


@when(parsers.parse('设置键 "{name}" 的 JSON 数据为 {json_name}'))
def when_set_json_named(name: str, json_name: str, bdd_context: dict[str, Any]) -> None:
    data = _JSON_SAMPLES[json_name]
    bdd_context["last_result"] = _run(bdd_context["op"].set_json(name, data))


@when(parsers.parse('设置键 "{name}" 的 NX JSON 数据为 {json_name}'))
def when_set_json_nx_named(name: str, json_name: str, bdd_context: dict[str, Any]) -> None:
    data = _JSON_SAMPLES[json_name]
    bdd_context["last_result"] = _run(bdd_context["op"].set_json(name, data, expire_seconds=5, nx=True))


@when(parsers.parse('获取键 "{name}" 的值'))
def when_get(name: str, bdd_context: dict[str, Any]) -> None:
    bdd_context["last_result"] = _run(bdd_context["op"].get(name, default="__notfound__"))


@when(parsers.parse('获取键 "{name}" 的 JSON 值'))
def when_get_json(name: str, bdd_context: dict[str, Any]) -> None:
    bdd_context["last_result"] = _run(bdd_context["op"].get_json(name))


@when(parsers.parse('获取键 "{name}" 的 TTL'))
def when_ttl(name: str, bdd_context: dict[str, Any]) -> None:
    bdd_context["last_result"] = _run(bdd_context["op"].ttl(name))


@when(parsers.parse('删除键 "{name}"'))
def when_delete(name: str, bdd_context: dict[str, Any]) -> None:
    bdd_context["last_result"] = _run(bdd_context["op"].delete(name))


@when(parsers.parse('检查键 "{name}" 是否存在'))
def when_exists(name: str, bdd_context: dict[str, Any]) -> None:
    bdd_context["last_result"] = _run(bdd_context["op"].exists(name))


@when(parsers.parse('将键 "{name}" 超时时间设为 "{seconds:d}" 秒'))
def when_expire(name: str, seconds: int, bdd_context: dict[str, Any]) -> None:
    bdd_context["last_result"] = _run(bdd_context["op"].expire(name, seconds))


@when(parsers.parse('等待 "{seconds:f}" 秒'))
def when_sleep(seconds: float) -> None:
    _run(asyncio.sleep(float(seconds)))


# ---------------------------------------------------------------------------
# When steps: 缓存操作
# ---------------------------------------------------------------------------


@when(parsers.parse('调用 cache_get_or_set 键 "{name}" 使用生产者返回 "{value}" 且 TTL 为 {ttl:d} 秒'))
def when_cache_get_or_set(name: str, value: str, ttl: int, bdd_context: dict[str, Any]) -> None:
    ctx = bdd_context
    ctx.setdefault("producer_calls", 0)

    async def producer() -> str:
        ctx["producer_calls"] += 1
        await asyncio.sleep(0)
        return value

    ctx["last_result"] = _run(ctx["op"].cache_get_or_set(name, producer, ttl=ttl, serializer=SerializationMode.JSON))


@when(parsers.parse('再次调用 cache_get_or_set 键 "{name}" 使用生产者返回 "{value}" 且 TTL 为 {ttl:d} 秒'))
def when_cache_get_or_set_again(name: str, value: str, ttl: int, bdd_context: dict[str, Any]) -> None:
    ctx = bdd_context

    async def producer() -> str:
        ctx["producer_calls"] += 1
        await asyncio.sleep(0)
        return value

    ctx["last_result"] = _run(ctx["op"].cache_get_or_set(name, producer, ttl=ttl, serializer=SerializationMode.JSON))


@when(parsers.parse('调用 cache_get_or_set 键 "{name}" 使用生产者返回 "{value}" 且强制调用生产者'))
def when_cache_get_or_set_force(name: str, value: str, bdd_context: dict[str, Any]) -> None:
    ctx = bdd_context

    async def producer() -> str:
        ctx["producer_calls"] += 1
        await asyncio.sleep(0)
        return value

    ctx["last_result"] = _run(
        ctx["op"].cache_get_or_set(name, producer, ttl=300, serializer=SerializationMode.JSON, force_call_producer=True)
    )


@when(parsers.parse('调用 cache_get_or_set 键 "{name}" 使用生产者返回 None 且不缓存 None'))
def when_cache_skip_none(name: str, bdd_context: dict[str, Any]) -> None:
    ctx = bdd_context
    ctx.setdefault("producer_calls", 0)

    async def producer() -> None:
        ctx["producer_calls"] += 1
        await asyncio.sleep(0)

    ctx["last_result"] = _run(
        ctx["op"].cache_get_or_set(name, producer, ttl=300, serializer=SerializationMode.JSON, null_value_strategy=RedisSkipNone())
    )


@when(parsers.parse('调用 cache_get_or_set 键 "{name}" 使用生产者返回 None 且缓存 None'))
def when_cache_all(name: str, bdd_context: dict[str, Any]) -> None:
    ctx = bdd_context
    ctx.setdefault("producer_calls", 0)

    async def producer() -> None:
        ctx["producer_calls"] += 1
        await asyncio.sleep(0)

    ctx["last_result"] = _run(
        ctx["op"].cache_get_or_set(name, producer, ttl=300, serializer=SerializationMode.JSON, null_value_strategy=RedisCacheAll())
    )


@when(parsers.parse('调用 cache_get_or_set 键 "{name}" 使用生产者返回 None 且 None 使用短 TTL'))
def when_cache_ttl_none(name: str, bdd_context: dict[str, Any]) -> None:
    ctx = bdd_context
    ctx.setdefault("producer_calls", 0)

    async def producer() -> None:
        ctx["producer_calls"] += 1
        await asyncio.sleep(0)

    ctx["last_result"] = _run(
        ctx["op"].cache_get_or_set(name, producer, ttl=300, serializer=SerializationMode.JSON, null_value_strategy=RedisTTLNone(1))
    )


# ---------------------------------------------------------------------------
# When steps: 节流/防抖
# ---------------------------------------------------------------------------


@when(parsers.parse('节流检查键 "{name}" 窗口 "{window:d}" 秒'))
def when_throttle(name: str, window: int, bdd_context: dict[str, Any]) -> None:
    bdd_context["last_result"] = _run(bdd_context["op"].throttle_check_and_set(name, window_seconds=window))


@when(parsers.parse('防抖检查键 "{name}" 窗口 "{window:d}" 秒'))
def when_debounce_check(name: str, window: int, bdd_context: dict[str, Any]) -> None:
    bdd_context["last_result"] = _run(bdd_context["op"].debounce_check_and_set(name, window_seconds=window))


@when(parsers.parse('防抖查询剩余时间键 "{name}"'))
def when_debounce_remaining(name: str, bdd_context: dict[str, Any]) -> None:
    bdd_context["last_result"] = _run(bdd_context["op"].debounce_get_remaining(name))


# ---------------------------------------------------------------------------
# When steps: 分布式锁
# ---------------------------------------------------------------------------


@when(parsers.parse('尝试获取分布式锁 "{name}" 超时 "{timeout:d}" 秒'))
def when_lock_acquire(name: str, timeout: int, bdd_context: dict[str, Any]) -> None:
    cm = bdd_context["op"].simple_distributed_lock(name, timeout)
    bdd_context["_lock_cm"] = cm
    bdd_context["last_result"] = _run(cm.__aenter__())


@when(parsers.parse('释放分布式锁 "{name}"'))
def when_lock_release(name: str, bdd_context: dict[str, Any]) -> None:
    cm = bdd_context.pop("_lock_cm", None)
    if cm is not None:
        _run(cm.__aexit__(None, None, None))
        bdd_context["last_result"] = "released"


@when(parsers.parse('在已持有锁 "{name}" 的情况下, 尝试再次获取分布式锁 "{name2}" 超时 "{timeout:d}" 秒'))
def when_lock_reacquire(name: str, name2: str, timeout: int, bdd_context: dict[str, Any]) -> None:
    cm = bdd_context["op"].simple_distributed_lock(name2, timeout)
    bdd_context["last_result"] = _run(cm.__aenter__())
    if not bdd_context["last_result"]:
        _run(cm.__aexit__(None, None, None))


# ---------------------------------------------------------------------------
# When steps: 批量操作 & 数据结构
# ---------------------------------------------------------------------------


@when(parsers.parse('批量获取键 "{k1}" 和 "{k2}"'))
def when_mget(k1: str, k2: str, bdd_context: dict[str, Any]) -> None:
    bdd_context["last_result"] = _run(bdd_context["op"].mget(k1, k2, serializer=SerializationMode.NONE))


@when(parsers.parse('批量设置键值: "{k1}" = "{v1}", "{k2}" = "{v2}"'))
def when_mset(k1: str, v1: str, k2: str, v2: str, bdd_context: dict[str, Any]) -> None:
    bdd_context["last_result"] = _run(bdd_context["op"].mset({k1: v1, k2: v2}))


@when(parsers.parse('哈希设置键 "{name}" 字段 "{field}" 值为 "{value}"'))
def when_hset(name: str, field: str, value: str, bdd_context: dict[str, Any]) -> None:
    bdd_context["last_result"] = _run(bdd_context["op"].hset(name, field, value))


@when(parsers.parse('哈希获取键 "{name}" 字段 "{field}"'))
def when_hget(name: str, field: str, bdd_context: dict[str, Any]) -> None:
    bdd_context["last_result"] = _run(bdd_context["op"].hget(name, field))


@when(parsers.parse('列表右推键 "{name}" 值 "{value}"'))
def when_rpush(name: str, value: str, bdd_context: dict[str, Any]) -> None:
    bdd_context["last_result"] = _run(bdd_context["op"].rpush(name, value))


@when(parsers.parse('集合添加键 "{name}" 值 "{value}"'))
def when_sadd(name: str, value: str, bdd_context: dict[str, Any]) -> None:
    bdd_context["last_result"] = _run(bdd_context["op"].sadd(name, value))


@when(parsers.parse('集合获取键 "{name}" 所有成员'))
def when_smembers(name: str, bdd_context: dict[str, Any]) -> None:
    bdd_context["last_result"] = _run(bdd_context["op"].smembers(name))


# ---------------------------------------------------------------------------
# Then steps: 通用断言
# ---------------------------------------------------------------------------


@then(parsers.parse("返回值为 JSON 且值等于 {json_name}"))
def then_value_is_json_named(json_name: str, bdd_context: dict[str, Any]) -> None:
    expected = _JSON_SAMPLES[json_name]
    assert bdd_context["last_result"] == expected, f"期望 {expected!r}, 实际 {bdd_context['last_result']!r}"


@then("返回结果应为 True")
def then_result_true(bdd_context: dict[str, Any]) -> None:
    assert bdd_context["last_result"] is True


@then("返回结果应为 False")
def then_result_false(bdd_context: dict[str, Any]) -> None:
    assert bdd_context["last_result"] is False


@then(parsers.parse('返回的值应为 "{expected}"'))
def then_value_equals(expected: str, bdd_context: dict[str, Any]) -> None:
    actual = bdd_context["last_result"]
    expected_typed = _coerce(expected, actual)
    assert actual == expected_typed, f"期望 {expected_typed!r}, 实际 {actual!r}"


@then("返回结果应为 None")
def then_result_none(bdd_context: dict[str, Any]) -> None:
    assert bdd_context["last_result"] is None


@then("返回结果不应为 None")
def then_result_not_none(bdd_context: dict[str, Any]) -> None:
    assert bdd_context["last_result"] is not None


@then(parsers.parse('返回结果为 DebounceResult 且 allowed 为 "{allowed}"'))
def then_debounce_allowed(allowed: str, bdd_context: dict[str, Any]) -> None:
    result: DebounceResult = bdd_context["last_result"]
    expected = allowed.lower() == "true"
    assert result.allowed is expected, f"期望 allowed={expected}, 实际 {result.allowed}"


@then(parsers.parse('返回结果为 DebounceResult 且 remaining_seconds > "{min_val:d}"'))
def then_debounce_remaining_gt(min_val: int, bdd_context: dict[str, Any]) -> None:
    result: DebounceResult = bdd_context["last_result"]
    assert result.remaining_seconds > min_val, f"期望 remaining_seconds > {min_val}, 实际 {result.remaining_seconds}"


@then(parsers.parse('返回结果为 JSON 且值等于 "{json_str}"'))
def then_json_equals(json_str: str, bdd_context: dict[str, Any]) -> None:
    expected = json.loads(json_str)
    assert bdd_context["last_result"] == expected, f"期望 {expected!r}, 实际 {bdd_context['last_result']!r}"


@then(parsers.parse('返回值的类型应为 "{type_name}"'))
def then_type_is(type_name: str, bdd_context: dict[str, Any]) -> None:
    type_map = {"int": int, "str": str, "dict": dict, "list": list, "set": set, "float": float, "bool": bool}
    expected_type = type_map.get(type_name, str)
    assert isinstance(bdd_context["last_result"], expected_type), f"期望类型 {expected_type}, 实际 {type(bdd_context['last_result'])}"


# ---------------------------------------------------------------------------
# Then steps: Redis 状态验证 (裸 Redis 操作)
# ---------------------------------------------------------------------------


@then(parsers.parse('原始键 "{raw_key}" 应存在'))
def then_raw_key_exists(raw_key: str, redis_mgr: AsyncRedisManager) -> None:
    exists = _run(_raw_exists(redis_mgr, raw_key))
    assert exists, f"原始键 {raw_key!r} 应存在"


@then(parsers.parse('原始键 "{raw_key}" 应不存在'))
def then_raw_key_not_exists(raw_key: str, redis_mgr: AsyncRedisManager) -> None:
    exists = _run(_raw_exists(redis_mgr, raw_key))
    assert not exists, f"原始键 {raw_key!r} 应不存在"


@then(parsers.parse('原始键 "{raw_key}" 的值应为 "{expected}"'))
def then_raw_value_equals(raw_key: str, expected: str, redis_mgr: AsyncRedisManager) -> None:
    actual = _run(_raw_get(redis_mgr, raw_key))
    assert actual == expected, f"原始键 {raw_key!r}: 期望 {expected!r}, 实际 {actual!r}"


@then(parsers.parse('原始键 "{raw_key}" 的 TTL 应大于 "{min_val:d}"'))
def then_raw_ttl_gt(raw_key: str, min_val: int, redis_mgr: AsyncRedisManager) -> None:
    ttl = _run(_raw_ttl(redis_mgr, raw_key))
    assert ttl > min_val, f"原始键 {raw_key!r}: 期望 TTL > {min_val}, 实际 {ttl}"


@then(parsers.parse('原始键 "{raw_key}" 的 TTL 应小于等于 "{max_val:d}"'))
def then_raw_ttl_le(raw_key: str, max_val: int, redis_mgr: AsyncRedisManager) -> None:
    ttl = _run(_raw_ttl(redis_mgr, raw_key))
    assert ttl <= max_val, f"原始键 {raw_key!r}: 期望 TTL <= {max_val}, 实际 {ttl}"


@then(parsers.parse('生产者应调用了 "{expected:d}" 次'))
def then_producer_calls(expected: int, bdd_context: dict[str, Any]) -> None:
    actual = bdd_context.get("producer_calls", 0)
    assert actual == expected, f"期望生产者调用 {expected} 次, 实际 {actual} 次"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _coerce(expected: str, actual: Any) -> Any:
    if actual is None:
        return None
    if isinstance(actual, int):
        return int(expected)
    if isinstance(actual, float):
        return float(expected)
    return expected
