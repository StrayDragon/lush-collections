import asyncio
import uuid
from datetime import timedelta

import pytest

from lush_redisx import (
    DEFAULT_CACHE_ALL_STRATEGY,
    DEFAULT_NULL_VALUE_STRATEGY,
    DEFAULT_SKIP_NONE_STRATEGY,
    DEFAULT_TTL_NONE_STRATEGY,
    AsyncRedisManager,
    DebounceResult,
    SerializationMode,
    build_cache_key,
)


@pytest.mark.asyncio
async def test_basic_kv_and_ttl(redis_mgr: AsyncRedisManager) -> None:
    key = "test:kv"
    assert await redis_mgr.op_prefixed.set(key, {"a": 1}, expire=1, serializer=SerializationMode.JSON)
    val = await redis_mgr.op_prefixed.get(key, serializer=SerializationMode.JSON)
    assert val == {"a": 1}
    ttl = await redis_mgr.op_prefixed.ttl(key)
    assert ttl >= 0
    await asyncio.sleep(1.1)
    assert await redis_mgr.op_prefixed.get(key, serializer=SerializationMode.JSON) is None


@pytest.mark.asyncio
async def test_json_ops(redis_mgr: AsyncRedisManager) -> None:
    key = "test:json"
    assert await redis_mgr.op_prefixed.set_json(key, {"x": 2}, expire_seconds=timedelta(seconds=10))
    data = await redis_mgr.op_prefixed.get_json(key)
    assert data == {"x": 2}


@pytest.mark.asyncio
async def test_hash_and_list_and_set(redis_mgr: AsyncRedisManager) -> None:
    # hash
    hkey = "test:h"
    _ = await redis_mgr.op_prefixed.delete(hkey)
    assert await redis_mgr.op_prefixed.hset(hkey, "f", {"k": 1}, serializer=SerializationMode.JSON)
    assert await redis_mgr.op_prefixed.hget(hkey, "f", serializer=SerializationMode.JSON) == {"k": 1}
    allv = await redis_mgr.op_prefixed.hgetall(hkey, serializer=SerializationMode.JSON)
    assert allv["f"] == {"k": 1}

    # list
    lkey = "test:l"
    _ = await redis_mgr.op_prefixed.delete(lkey)
    _ = await redis_mgr.op_prefixed.rpush(lkey, 1, 2, serializer=SerializationMode.JSON)
    _ = await redis_mgr.op_prefixed.lpush(lkey, 0, serializer=SerializationMode.JSON)
    vals = await redis_mgr.op_prefixed.lrange(lkey, 0, -1, serializer=SerializationMode.JSON)
    assert vals == [0, 1, 2]
    popped = await redis_mgr.op_prefixed.lpop(lkey, serializer=SerializationMode.JSON)
    assert popped == 0

    # set
    skey = "test:s"
    _ = await redis_mgr.op_prefixed.delete(skey)
    added = await redis_mgr.op_prefixed.sadd(skey, 1, 2, 2, serializer=SerializationMode.JSON)
    assert added >= 1
    members = await redis_mgr.op_prefixed.smembers(skey, serializer=SerializationMode.JSON)
    assert members.issuperset({1, 2})


@pytest.mark.asyncio
async def test_lpop_with_count(redis_mgr: AsyncRedisManager) -> None:
    key = "test:l:count"
    _ = await redis_mgr.op_prefixed.delete(key)
    _ = await redis_mgr.op_prefixed.rpush(key, 1, 2, 3, serializer=SerializationMode.JSON)
    _ = await redis_mgr.op_prefixed.lpush(key, 0, serializer=SerializationMode.JSON)

    popped = await redis_mgr.op_prefixed.lpop(key, count=2, serializer=SerializationMode.JSON)
    assert popped == [0, 1]

    remain = await redis_mgr.op_prefixed.lrange(key, 0, -1, serializer=SerializationMode.JSON)
    assert remain == [2, 3]

    # missing key with default list
    popped2 = await redis_mgr.op_prefixed.lpop("test:l:missing-count", default=[], count=2, serializer=SerializationMode.JSON)
    assert popped2 == []


@pytest.mark.asyncio
async def test_mget_mset_and_delete_and_exists(redis_mgr: AsyncRedisManager) -> None:
    m = {"test:m:1": 1, "test:m:2": {"a": 2}}
    assert await redis_mgr.op_prefixed.mset(m, serializer=SerializationMode.JSON)
    vals = await redis_mgr.op_prefixed.mget(*m.keys(), serializer=SerializationMode.JSON)
    assert vals[0] == 1
    assert vals[1] == {"a": 2}
    assert await redis_mgr.op_prefixed.exists(*m.keys()) >= 1
    deleted = await redis_mgr.op_prefixed.delete(*m.keys())
    assert deleted >= 1


@pytest.mark.asyncio
async def test_set_and_get_without_pipeline(redis_mgr: AsyncRedisManager) -> None:
    key = "test:p"
    assert await redis_mgr.op_prefixed.set(key, "v")
    v = await redis_mgr.op_prefixed.get(key)
    assert v == "v"


@pytest.mark.asyncio
async def test_expire_and_ttl_variants(redis_mgr: AsyncRedisManager) -> None:
    key = "test:expire"
    assert await redis_mgr.op_prefixed.set(key, 1)
    assert await redis_mgr.op_prefixed.expire(key, 1) is True
    ttl1 = await redis_mgr.op_prefixed.ttl(key)
    assert ttl1 >= 0
    await asyncio.sleep(1.1)
    assert await redis_mgr.op_prefixed.get(key) is None

    # 再次设置并使用 timedelta
    assert await redis_mgr.op_prefixed.set(key, 2)
    assert await redis_mgr.op_prefixed.expire(key, timedelta(seconds=1)) is True
    ttl2 = await redis_mgr.op_prefixed.ttl(key)
    assert ttl2 >= 0


@pytest.mark.asyncio
async def test_set_json_nx_and_xx(redis_mgr: AsyncRedisManager) -> None:
    key = "test:json:nx"
    await redis_mgr.op_prefixed.delete(key)
    assert await redis_mgr.op_prefixed.set_json(key, {"a": 1}, expire_seconds=5, nx=True) is True
    # 再次 NX 应失败
    assert await redis_mgr.op_prefixed.set_json(key, {"a": 2}, expire_seconds=5, nx=True) is False
    # XX 存在时应成功
    assert await redis_mgr.op_prefixed.set_json(key, {"a": 3}, expire_seconds=5, xx=True) is True
    val = await redis_mgr.op_prefixed.get_json(key)
    assert val == {"a": 3}


# 移除: 不再支持 pickle 回退


@pytest.mark.asyncio
async def test_lpop_default_and_smembers_empty_exists_zero(redis_mgr: AsyncRedisManager) -> None:
    lkey = "test:l:missing"
    assert await redis_mgr.op_prefixed.lpop(lkey) is None

    skey = "test:s:missing"
    members = await redis_mgr.op_prefixed.smembers(skey)
    assert isinstance(members, set)
    assert len(members) == 0

    assert await redis_mgr.op_prefixed.exists("test:missing:1", "test:missing:2") == 0


@pytest.mark.asyncio
async def test_delete_and_expire_nonexistent(redis_mgr: AsyncRedisManager) -> None:
    key = "test:nonexist"
    assert await redis_mgr.op_prefixed.delete(key) == 0
    assert await redis_mgr.op_prefixed.expire(key, 10) is False


# =====================
# 新增: 缓存能力测试
# =====================


@pytest.mark.asyncio
async def test_cache_get_or_set_basic_and_skip_none(redis_mgr: AsyncRedisManager) -> None:
    # 基本命中
    key = build_cache_key("ut:cache", "basic", 1)
    _ = await redis_mgr.op_prefixed.delete(key)

    call_count = 0

    async def producer() -> dict[str, int]:
        nonlocal call_count
        call_count += 1
        return {"v": call_count}

    v1 = await redis_mgr.op_prefixed.cache_get_or_set(
        key,
        producer=producer,
        ttl=300,
        serializer=SerializationMode.JSON,
    )
    assert v1 == {"v": 1}

    v2 = await redis_mgr.op_prefixed.cache_get_or_set(
        key,
        producer=producer,
        ttl=300,
        serializer=SerializationMode.JSON,
    )
    assert v2 == {"v": 1}
    assert call_count == 1  # 第二次命中缓存, 不再调用 producer

    # skip_none=True: 不缓存 None, 每次都会调用 producer
    key2 = build_cache_key("ut:cache", "skipnone", 1)
    _ = await redis_mgr.op_prefixed.delete(key2)

    call_count2 = 0

    async def producer_none() -> None:
        nonlocal call_count2
        call_count2 += 1

    from lush_redisx import RedisCacheAll, RedisSkipNone

    n1 = await redis_mgr.op_prefixed.cache_get_or_set(
        key2,
        producer=producer_none,
        ttl=300,
        serializer=SerializationMode.JSON,
        null_value_strategy=RedisSkipNone(),
    )
    n2 = await redis_mgr.op_prefixed.cache_get_or_set(
        key2,
        producer=producer_none,
        ttl=300,
        serializer=SerializationMode.JSON,
        null_value_strategy=RedisSkipNone(),
    )
    assert n1 is None
    assert n2 is None
    assert call_count2 == 2

    # skip_none=False: 会缓存 None, 第二次不再调用 producer
    key3 = build_cache_key("ut:cache", "cachenone", 1)
    _ = await redis_mgr.op_prefixed.delete(key3)

    call_count3 = 0

    async def producer_none_cached() -> None:
        nonlocal call_count3
        call_count3 += 1

    _n1 = await redis_mgr.op_prefixed.cache_get_or_set(
        key3,
        producer=producer_none_cached,
        ttl=300,
        serializer=SerializationMode.JSON,
        null_value_strategy=RedisCacheAll(),
    )
    _n2 = await redis_mgr.op_prefixed.cache_get_or_set(
        key3,
        producer=producer_none_cached,
        ttl=300,
        serializer=SerializationMode.JSON,
        null_value_strategy=RedisCacheAll(),
    )
    assert call_count3 == 1


@pytest.mark.asyncio
async def test_cache_get_or_set_force_call_producer(redis_mgr: AsyncRedisManager) -> None:
    key = build_cache_key("ut:cache", "force", 1)
    _ = await redis_mgr.op_prefixed.delete(key)

    call_count = 0

    async def producer() -> dict[str, int]:
        nonlocal call_count
        call_count += 1
        return {"v": call_count}

    # 先写入缓存
    v1 = await redis_mgr.op_prefixed.cache_get_or_set(key, producer=producer, ttl=300, serializer=SerializationMode.JSON)
    assert v1 == {"v": 1}
    assert call_count == 1

    # 即使缓存已存在, force_call_producer=True 仍会再次调用 producer 并覆盖缓存
    v2 = await redis_mgr.op_prefixed.cache_get_or_set(
        key,
        producer=producer,
        ttl=300,
        serializer=SerializationMode.JSON,
        force_call_producer=True,
    )
    assert v2 == {"v": 2}
    assert call_count == 2

    # 再次读取应命中新值
    v3 = await redis_mgr.op_prefixed.cache_get_or_set(key, producer=producer, ttl=300, serializer=SerializationMode.JSON)
    assert v3 == {"v": 2}
    assert call_count == 2


@pytest.mark.asyncio
async def test_cache_get_or_set_ttl_expire(redis_mgr: AsyncRedisManager) -> None:
    key = build_cache_key("ut:cache", "ttl", 1)
    _ = await redis_mgr.op_prefixed.delete(key)

    call_count = 0

    async def producer() -> dict[str, int]:
        nonlocal call_count
        call_count += 1
        return {"v": call_count}

    v1 = await redis_mgr.op_prefixed.cache_get_or_set(key, producer=producer, ttl=1, serializer=SerializationMode.JSON)
    assert v1 == {"v": 1}
    await asyncio.sleep(1.1)
    v2 = await redis_mgr.op_prefixed.cache_get_or_set(key, producer=producer, ttl=1, serializer=SerializationMode.JSON)
    assert v2 == {"v": 2}
    assert call_count == 2


@pytest.mark.asyncio
async def test_cache_get_or_set_with_default_constants(redis_mgr: AsyncRedisManager) -> None:
    # DEFAULT_NULL_VALUE_STRATEGY / DEFAULT_SKIP_NONE_STRATEGY: 不缓存 None
    key1 = build_cache_key("ut:cache", "const", "skip")
    _ = await redis_mgr.op_prefixed.delete(key1)

    calls1 = 0

    async def prod_none1() -> None:
        nonlocal calls1
        calls1 += 1

    _ = await redis_mgr.op_prefixed.cache_get_or_set(
        key1,
        producer=prod_none1,
        ttl=300,
        serializer=SerializationMode.JSON,
        null_value_strategy=DEFAULT_NULL_VALUE_STRATEGY,
    )
    _ = await redis_mgr.op_prefixed.cache_get_or_set(
        key1,
        producer=prod_none1,
        ttl=300,
        serializer=SerializationMode.JSON,
        null_value_strategy=DEFAULT_SKIP_NONE_STRATEGY,
    )
    assert calls1 == 2

    # DEFAULT_CACHE_ALL_STRATEGY: 缓存 None
    key2 = build_cache_key("ut:cache", "const", "all")
    _ = await redis_mgr.op_prefixed.delete(key2)

    calls2 = 0

    async def prod_none2() -> None:
        nonlocal calls2
        calls2 += 1

    _ = await redis_mgr.op_prefixed.cache_get_or_set(
        key2,
        producer=prod_none2,
        ttl=300,
        serializer=SerializationMode.JSON,
        null_value_strategy=DEFAULT_CACHE_ALL_STRATEGY,
    )
    _ = await redis_mgr.op_prefixed.cache_get_or_set(
        key2,
        producer=prod_none2,
        ttl=300,
        serializer=SerializationMode.JSON,
        null_value_strategy=DEFAULT_CACHE_ALL_STRATEGY,
    )
    assert calls2 == 1

    # DEFAULT_TTL_NONE_STRATEGY: None 使用短 TTL
    key3 = build_cache_key("ut:cache", "const", "ttlNone")
    _ = await redis_mgr.op_prefixed.delete(key3)

    calls3 = 0

    async def prod_none3() -> None:
        nonlocal calls3
        calls3 += 1

    _ = await redis_mgr.op_prefixed.cache_get_or_set(
        key3,
        producer=prod_none3,
        ttl=300,
        serializer=SerializationMode.JSON,
        null_value_strategy=DEFAULT_TTL_NONE_STRATEGY,
    )
    _ = await redis_mgr.op_prefixed.cache_get_or_set(
        key3,
        producer=prod_none3,
        ttl=300,
        serializer=SerializationMode.JSON,
        null_value_strategy=DEFAULT_TTL_NONE_STRATEGY,
    )
    assert calls3 == 1
    await asyncio.sleep(1.1)
    _ = await redis_mgr.op_prefixed.cache_get_or_set(
        key3,
        producer=prod_none3,
        ttl=300,
        serializer=SerializationMode.JSON,
        null_value_strategy=DEFAULT_TTL_NONE_STRATEGY,
    )
    assert calls3 == 2


@pytest.mark.asyncio
async def test_async_cached_with_decorator(redis_mgr: AsyncRedisManager) -> None:
    count = 0

    def key_builder(a: str, b: int) -> str:
        return build_cache_key("ut:decor", a, b)

    @redis_mgr.op_prefixed.async_cached_with(key_builder, ttl=120, serializer=SerializationMode.JSON)
    async def compute(a: str, b: int) -> dict[str, int]:
        nonlocal count
        count += 1
        return {"cnt": count, "out": b}

    # 确保干净
    _ = await redis_mgr.op_prefixed.delete(key_builder("A", 7))

    r1 = await compute("A", 7)
    assert r1 == {"cnt": 1, "out": 7}
    r2 = await compute("A", 7)
    assert r2 == {"cnt": 1, "out": 7}
    assert count == 1


@pytest.mark.asyncio
async def test_key_builder_partial_args_ok(redis_mgr: AsyncRedisManager) -> None:
    # key_builder 只用到部分参数: 只取第一个参数
    count = 0

    def key_builder(a: str, b: int) -> str:
        return build_cache_key("ut:decor-partial", a)

    @redis_mgr.op_prefixed.async_cached_with(key_builder, ttl=60, serializer=SerializationMode.JSON)
    async def compute(a: str, b: int) -> dict[str, int]:
        nonlocal count
        count += 1
        return {"cnt": count, "out": b}

    # 不同的第二参数 b, 因 key 只使用 a, 应命中同一缓存
    _ = await redis_mgr.op_prefixed.delete(build_cache_key("ut:decor-partial", "A"))
    r1 = await compute("A", 1)
    r2 = await compute("A", 2)
    assert r1 == {"cnt": 1, "out": 1}
    # 命中缓存, 出参完全来自第一次执行
    assert r2 == {"cnt": 1, "out": 1}
    assert count == 1


@pytest.mark.asyncio
async def test_key_builder_partial_args_missing_kwargs_error(redis_mgr: AsyncRedisManager) -> None:
    # key_builder 需要的参数缺失会抛 TypeError
    def key_builder(a: str, b: int) -> str:
        return build_cache_key("ut:decor-partial-err", a, b)

    @redis_mgr.op_prefixed.async_cached_with(key_builder, ttl=60, serializer=SerializationMode.JSON)
    async def compute(a: str, b: int) -> int:
        return b

    _ = await redis_mgr.op_prefixed.delete(build_cache_key("ut:decor-partial-err", "A", 1))
    # 故意缺少参数 b 传递给被包装函数, wrapper 会把参数原样转发给 key_builder, 因而触发 TypeError
    from typing import Any, cast

    with pytest.raises(TypeError):
        _ = await cast("Any", compute)("A")


@pytest.mark.asyncio
async def test_key_builder_partial_args_with_defaults_ok(redis_mgr: AsyncRedisManager) -> None:
    # key_builder 依赖 b, 但提供了默认值; compute 也为 b 提供默认值
    count = 0

    def key_builder(a: str, b: int = 10) -> str:
        return build_cache_key("ut:decor-partial-def", a, b)

    @redis_mgr.op_prefixed.async_cached_with(key_builder, ttl=60, serializer=SerializationMode.JSON)
    async def compute(a: str, b: int = 10) -> dict[str, int]:
        nonlocal count
        count += 1
        return {"cnt": count, "out": b}

    # 未提供 b, 使用默认 10, 不报错
    _ = await redis_mgr.op_prefixed.delete(build_cache_key("ut:decor-partial-def", "A", 10))
    r1 = await compute("A")
    r2 = await compute("A")
    assert r1 == {"cnt": 1, "out": 10}
    assert r2 == {"cnt": 1, "out": 10}
    assert count == 1

    # 更换 key, 触发重新计算
    r3 = await compute("A", 8)
    assert r3 == {"cnt": 2, "out": 8}


def test_build_cache_key_helper() -> None:
    k = build_cache_key("p", "a", 1, None, "b")
    assert k == "p:a:1:b"


@pytest.mark.asyncio
async def test_async_cached_with_instance_method(redis_mgr: AsyncRedisManager) -> None:
    def make_service(mgr: AsyncRedisManager):
        class S:
            def __init__(self) -> None:
                self.count = 0

            @mgr.op_prefixed.async_cached_with(
                lambda self, a: build_cache_key("ut:imethod", a),
                ttl=120,
                serializer=SerializationMode.JSON,
            )
            async def calc(self, a: int) -> dict[str, int]:
                self.count += 1
                return {"cnt": self.count, "a": a}

        return S

    Svc = make_service(redis_mgr)
    s = Svc()
    # 确保干净
    _ = await redis_mgr.op_prefixed.delete(build_cache_key("ut:imethod", 7))

    r1 = await s.calc(7)
    assert r1 == {"cnt": 1, "a": 7}
    r2 = await s.calc(7)
    assert r2 == {"cnt": 1, "a": 7}
    # 更换参数
    r3 = await s.calc(8)
    assert r3 == {"cnt": 2, "a": 8}


@pytest.mark.asyncio
async def test_async_cached_with_class_method(redis_mgr: AsyncRedisManager) -> None:
    def make_service(mgr: AsyncRedisManager):
        class S:
            _ccount: int = 0

            @classmethod
            @mgr.op_prefixed.async_cached_with(
                lambda cls, a: build_cache_key("ut:cmethod", a),
                ttl=120,
                serializer=SerializationMode.JSON,
            )
            async def ccalc(cls, a: int) -> dict[str, int]:
                cls._ccount += 1
                return {"cnt": cls._ccount, "a": a}

        return S

    Svc = make_service(redis_mgr)
    # 清理
    _ = await redis_mgr.op_prefixed.delete(build_cache_key("ut:cmethod", 5))

    r1 = await Svc.ccalc(5)
    assert r1 == {"cnt": 1, "a": 5}
    r2 = await Svc.ccalc(5)
    assert r2 == {"cnt": 1, "a": 5}
    # 参数变化 => 重新计算
    r3 = await Svc.ccalc(6)
    assert r3 == {"cnt": 2, "a": 6}


@pytest.mark.asyncio
async def test_cache_get_or_set_none_strategy_ttl_none(redis_mgr: AsyncRedisManager) -> None:
    from lush_redisx import RedisTTLNone

    key = build_cache_key("ut:cache", "ttl-none", 1)
    _ = await redis_mgr.op_prefixed.delete(key)

    calls = 0

    async def prod_none() -> None:
        nonlocal calls
        calls += 1

    n1 = await redis_mgr.op_prefixed.cache_get_or_set(
        key,
        producer=prod_none,
        ttl=300,
        serializer=SerializationMode.JSON,
        null_value_strategy=RedisTTLNone(1),
    )
    assert n1 is None

    # TTL 未过期, 命中缓存, 不再调用 producer
    n2 = await redis_mgr.op_prefixed.cache_get_or_set(
        key,
        producer=prod_none,
        ttl=300,
        serializer=SerializationMode.JSON,
        null_value_strategy=RedisTTLNone(1),
    )
    assert n2 is None
    assert calls == 1

    # 等待过期, 触发重新计算
    await asyncio.sleep(1.1)
    n3 = await redis_mgr.op_prefixed.cache_get_or_set(
        key,
        producer=prod_none,
        ttl=300,
        serializer=SerializationMode.JSON,
        null_value_strategy=RedisTTLNone(1),
    )
    assert n3 is None
    assert calls == 2


@pytest.mark.asyncio
async def test_cache_get_or_set_none_strategy_bool_variants(redis_mgr: AsyncRedisManager) -> None:
    from lush_redisx import RedisCacheAll, RedisSkipNone

    # RedisSkipNone: 不缓存 None
    key_t = build_cache_key("ut:cache", "strategy-bool", "T")
    _ = await redis_mgr.op_prefixed.delete(key_t)

    calls_t = 0

    async def prod_none_t() -> None:
        nonlocal calls_t
        calls_t += 1

    _ = await redis_mgr.op_prefixed.cache_get_or_set(
        key_t,
        producer=prod_none_t,
        ttl=300,
        serializer=SerializationMode.JSON,
        null_value_strategy=RedisSkipNone(),
    )
    _ = await redis_mgr.op_prefixed.cache_get_or_set(
        key_t,
        producer=prod_none_t,
        ttl=300,
        serializer=SerializationMode.JSON,
        null_value_strategy=RedisSkipNone(),
    )
    assert calls_t == 2

    # RedisCacheAll: 缓存 None(默认 TTL)
    key_f = build_cache_key("ut:cache", "strategy-bool", "F")
    _ = await redis_mgr.op_prefixed.delete(key_f)

    calls_f = 0

    async def prod_none_f() -> None:
        nonlocal calls_f
        calls_f += 1

    _ = await redis_mgr.op_prefixed.cache_get_or_set(
        key_f,
        producer=prod_none_f,
        ttl=300,
        serializer=SerializationMode.JSON,
        null_value_strategy=RedisCacheAll(),
    )
    _ = await redis_mgr.op_prefixed.cache_get_or_set(
        key_f,
        producer=prod_none_f,
        ttl=300,
        serializer=SerializationMode.JSON,
        null_value_strategy=RedisCacheAll(),
    )
    assert calls_f == 1


@pytest.mark.asyncio
async def test_async_cached_with_strategy(redis_mgr: AsyncRedisManager) -> None:
    from lush_redisx import RedisTTLNone

    def make_service(mgr: AsyncRedisManager):
        class S:
            def __init__(self) -> None:
                self.count = 0

            @mgr.op_prefixed.async_cached_with(
                lambda self, a: build_cache_key("ut:decor-strategy", a),
                ttl=120,
                serializer=SerializationMode.JSON,
                null_value_strategy=RedisTTLNone(1),
            )
            async def calc(self, a: int) -> None:
                self.count += 1

        return S

    Svc = make_service(redis_mgr)
    s = Svc()
    _ = await redis_mgr.op_prefixed.delete(build_cache_key("ut:decor-strategy", 9))

    r1 = await s.calc(9)
    assert r1 is None
    r2 = await s.calc(9)
    assert r2 is None
    assert s.count == 1

    await asyncio.sleep(1.1)
    r3 = await s.calc(9)
    assert r3 is None
    assert s.count == 2


@pytest.mark.asyncio
async def test_serialization_string_mode(redis_mgr: AsyncRedisManager) -> None:
    key = "test:set:string"
    _ = await redis_mgr.op_prefixed.delete(key)
    # 以 STRING 模式写入数字
    assert await redis_mgr.op_prefixed.set(key, 123, serializer=SerializationMode.STRING)
    # NONE 读取应返回字符串形式
    v_raw = await redis_mgr.op_prefixed.get(key, serializer=SerializationMode.NONE)
    assert v_raw == "123"
    # STRING 读取同样是字符串
    v_str = await redis_mgr.op_prefixed.get(key, serializer=SerializationMode.STRING)
    assert v_str == "123"


@pytest.mark.asyncio
async def test_get_json_invalid_and_pipeline_error(redis_mgr: AsyncRedisManager) -> None:
    key = "test:json:invalid"
    _ = await redis_mgr.op_prefixed.delete(key)
    # 写入非 JSON 文本
    assert await redis_mgr.op_prefixed.set(key, "not-json", serializer=SerializationMode.STRING)
    # 读取时提供默认值,应走 JSONDecodeError 分支
    v = await redis_mgr.op_prefixed.get_json(key, default={"d": 1})
    assert v == {"d": 1}

    # pipeline 场景已移除


@pytest.mark.asyncio
async def test_wrongtype_errors_cover_except_paths(redis_mgr: AsyncRedisManager) -> None:
    # GET on a list -> WRONGTYPE triggers get() except
    k_list = "ut:wrong:get"
    _ = await redis_mgr.op_prefixed.delete(k_list)
    _ = await redis_mgr.op_prefixed.lpush(k_list, 1)
    v = await redis_mgr.op_prefixed.get(k_list, default="d")
    assert v == "d"

    # Hash ops on string -> WRONGTYPE
    k_str = "ut:wrong:hash"
    _ = await redis_mgr.op_prefixed.delete(k_str)
    assert await redis_mgr.op_prefixed.set(k_str, "v")
    assert await redis_mgr.op_prefixed.hget(k_str, "f", default=9) == 9
    assert await redis_mgr.op_prefixed.hset(k_str, "f", 1) is False
    assert await redis_mgr.op_prefixed.hgetall(k_str) == {}

    # List ops on string -> WRONGTYPE
    k_str2 = "ut:wrong:list"
    _ = await redis_mgr.op_prefixed.delete(k_str2)
    assert await redis_mgr.op_prefixed.set(k_str2, "v")
    assert await redis_mgr.op_prefixed.lpush(k_str2, 1) == 0
    assert await redis_mgr.op_prefixed.rpush(k_str2, 1) == 0
    assert await redis_mgr.op_prefixed.lpop(k_str2, default=None) is None
    assert await redis_mgr.op_prefixed.lrange(k_str2, 0, -1) == []

    # Set ops on string -> WRONGTYPE
    k_str3 = "ut:wrong:set"
    _ = await redis_mgr.op_prefixed.delete(k_str3)
    assert await redis_mgr.op_prefixed.set(k_str3, "v")
    assert await redis_mgr.op_prefixed.sadd(k_str3, 1) == 0
    assert await redis_mgr.op_prefixed.smembers(k_str3) == set()


@pytest.mark.asyncio
async def test_after_close_still_operable_but_set_json_typeerror(redis_mgr: AsyncRedisManager) -> None:
    await redis_mgr.close()
    # 关闭后客户端可能自行重连,不强求 except 分支; 仅验证 set_json TypeError 仍被捕获
    assert await redis_mgr.op_prefixed.set_json("k", set()) is False  # json.dumps(set()) -> TypeError


@pytest.mark.asyncio
async def test_cache_ttlnone_with_timedelta(redis_mgr: AsyncRedisManager) -> None:
    key = build_cache_key("ut:cache", "ttl", "timedelta")
    _ = await redis_mgr.op_prefixed.delete(key)

    from lush_redisx import RedisTTLNone

    calls = 0

    async def prod_none() -> None:
        nonlocal calls
        calls += 1

    n1 = await redis_mgr.op_prefixed.cache_get_or_set(
        key,
        producer=prod_none,
        ttl=300,
        serializer=SerializationMode.JSON,
        null_value_strategy=RedisTTLNone(timedelta(seconds=1)),
    )
    assert n1 is None
    await asyncio.sleep(1.1)
    _ = await redis_mgr.op_prefixed.cache_get_or_set(
        key,
        producer=prod_none,
        ttl=300,
        serializer=SerializationMode.JSON,
        null_value_strategy=RedisTTLNone(timedelta(seconds=1)),
    )
    assert calls == 2


# ========== 防抖功能测试 ==========


@pytest.mark.asyncio
async def test_debounce_check_and_set_first_allow(redis_mgr: AsyncRedisManager) -> None:
    """测试首次调用应该允许"""
    key = "test:debounce:first_allow"
    _ = await redis_mgr.op_prefixed.delete(key)

    result = await redis_mgr.op_prefixed.debounce_check_and_set(key, window_seconds=10)

    assert isinstance(result, DebounceResult)
    assert result.allowed is True
    assert result.remaining_seconds == 0.0
    assert key in result.redis_key


@pytest.mark.asyncio
async def test_debounce_check_and_set_second_deny(redis_mgr: AsyncRedisManager) -> None:
    """测试时间窗口内第二次调用应该拒绝"""
    key = "test:debounce:second_deny"
    _ = await redis_mgr.op_prefixed.delete(key)

    # 第一次调用 - 应该允许
    result1 = await redis_mgr.op_prefixed.debounce_check_and_set(key, window_seconds=10)
    assert result1.allowed is True

    # 第二次调用 - 应该拒绝
    result2 = await redis_mgr.op_prefixed.debounce_check_and_set(key, window_seconds=10)
    assert result2.allowed is False
    assert result2.remaining_seconds > 0
    assert result2.remaining_seconds <= 10


@pytest.mark.asyncio
async def test_debounce_check_and_set_after_expiry(redis_mgr: AsyncRedisManager) -> None:
    """测试过期后应该再次允许"""
    key = "test:debounce:after_expiry"
    _ = await redis_mgr.op_prefixed.delete(key)

    # 第一次调用 - 允许
    result1 = await redis_mgr.op_prefixed.debounce_check_and_set(key, window_seconds=1)
    assert result1.allowed is True

    # 立即第二次调用 - 拒绝
    result2 = await redis_mgr.op_prefixed.debounce_check_and_set(key, window_seconds=1)
    assert result2.allowed is False

    # 等待过期
    await asyncio.sleep(1.2)

    # 过期后第三次调用 - 应该允许
    result3 = await redis_mgr.op_prefixed.debounce_check_and_set(key, window_seconds=1)
    assert result3.allowed is True


@pytest.mark.asyncio
async def test_debounce_get_remaining_no_key(redis_mgr: AsyncRedisManager) -> None:
    """测试查询不存在的 key 应该返回 allowed=True"""
    key = "test:debounce:no_key"
    _ = await redis_mgr.op_prefixed.delete(key)

    result = await redis_mgr.op_prefixed.debounce_get_remaining(key)

    assert result.allowed is True
    assert result.remaining_seconds == 0.0


@pytest.mark.asyncio
async def test_debounce_get_remaining_existing_key(redis_mgr: AsyncRedisManager) -> None:
    """测试查询存在的 key 应该返回正确的剩余时间"""
    key = "test:debounce:existing_key"
    _ = await redis_mgr.op_prefixed.delete(key)

    # 先设置防抖
    _ = await redis_mgr.op_prefixed.debounce_check_and_set(key, window_seconds=10)

    # 查询剩余时间
    result = await redis_mgr.op_prefixed.debounce_get_remaining(key)

    assert result.allowed is False
    assert result.remaining_seconds > 0
    assert result.remaining_seconds <= 10


@pytest.mark.asyncio
async def test_debounce_action_global(redis_mgr: AsyncRedisManager) -> None:
    """测试全局防抖(无分组)"""
    action = "test_action_global"
    # 清理可能存在的 key
    key = f"debounce:{action}"
    _ = await redis_mgr.op_prefixed.delete(key)

    # 第一次调用 - 允许
    result1 = await redis_mgr.op_prefixed.debounce_action(action, window_seconds=10)
    assert result1.allowed is True

    # 第二次调用 - 拒绝
    result2 = await redis_mgr.op_prefixed.debounce_action(action, window_seconds=10)
    assert result2.allowed is False


@pytest.mark.asyncio
async def test_debounce_action_single_group(redis_mgr: AsyncRedisManager) -> None:
    """测试单维度分组防抖"""
    action = "test_action_single"
    group1 = "user:123"
    group2 = "user:456"

    # 清理
    _ = await redis_mgr.op_prefixed.delete(f"debounce:{action}:{group1}")
    _ = await redis_mgr.op_prefixed.delete(f"debounce:{action}:{group2}")

    # group1 第一次 - 允许
    result1 = await redis_mgr.op_prefixed.debounce_action(action, window_seconds=10, group_by=group1)
    assert result1.allowed is True

    # group1 第二次 - 拒绝
    result2 = await redis_mgr.op_prefixed.debounce_action(action, window_seconds=10, group_by=group1)
    assert result2.allowed is False

    # group2 第一次 - 允许(不同分组独立)
    result3 = await redis_mgr.op_prefixed.debounce_action(action, window_seconds=10, group_by=group2)
    assert result3.allowed is True


@pytest.mark.asyncio
async def test_debounce_action_multi_group(redis_mgr: AsyncRedisManager) -> None:
    """测试多维度分组防抖"""
    action = "test_action_multi"
    groups = ["client:203.0.113.10", "script:sync"]

    # 清理
    key = f"debounce:{action}:{groups[0]}:{groups[1]}"
    _ = await redis_mgr.op_prefixed.delete(key)

    # 第一次 - 允许
    result1 = await redis_mgr.op_prefixed.debounce_action(action, window_seconds=10, group_by=groups)
    assert result1.allowed is True

    # 第二次 - 拒绝
    result2 = await redis_mgr.op_prefixed.debounce_action(action, window_seconds=10, group_by=groups)
    assert result2.allowed is False


@pytest.mark.asyncio
async def test_debounce_action_group_by_invalid_type(redis_mgr: AsyncRedisManager) -> None:
    action = "test_action_group_by_invalid_type"
    _ = await redis_mgr.op_prefixed.delete(f"debounce:{action}")

    from typing import Any, cast

    group_by = cast("Any", ("not-a", "list"))

    r1 = await redis_mgr.op_prefixed.debounce_action(action, window_seconds=10, group_by=group_by)
    assert r1.allowed is True

    r2 = await redis_mgr.op_prefixed.debounce_action(action, window_seconds=10, group_by=group_by)
    assert r2.allowed is False


@pytest.mark.asyncio
async def test_debounce_action_different_groups_independent(redis_mgr: AsyncRedisManager) -> None:
    """测试不同分组之间相互独立"""
    action = "test_action_independent"
    group_a = ["type:a", "id:1"]
    group_b = ["type:b", "id:1"]

    # 清理
    _ = await redis_mgr.op_prefixed.delete(f"debounce:{action}:{group_a[0]}:{group_a[1]}")
    _ = await redis_mgr.op_prefixed.delete(f"debounce:{action}:{group_b[0]}:{group_b[1]}")

    # group_a 触发防抖
    result_a1 = await redis_mgr.op_prefixed.debounce_action(action, window_seconds=10, group_by=group_a)
    assert result_a1.allowed is True

    result_a2 = await redis_mgr.op_prefixed.debounce_action(action, window_seconds=10, group_by=group_a)
    assert result_a2.allowed is False

    # group_b 不受影响
    result_b1 = await redis_mgr.op_prefixed.debounce_action(action, window_seconds=10, group_by=group_b)
    assert result_b1.allowed is True


@pytest.mark.asyncio
async def test_debounce_concurrent_requests(redis_mgr: AsyncRedisManager) -> None:
    """测试并发请求时只有一个能通过"""
    key = "test:debounce:concurrent"
    _ = await redis_mgr.op_prefixed.delete(key)

    # 并发执行多个请求
    results = await asyncio.gather(
        redis_mgr.op_prefixed.debounce_check_and_set(key, window_seconds=10),
        redis_mgr.op_prefixed.debounce_check_and_set(key, window_seconds=10),
        redis_mgr.op_prefixed.debounce_check_and_set(key, window_seconds=10),
        redis_mgr.op_prefixed.debounce_check_and_set(key, window_seconds=10),
        redis_mgr.op_prefixed.debounce_check_and_set(key, window_seconds=10),
    )

    # 只有一个应该被允许
    allowed_count = sum(1 for r in results if r.allowed)
    assert allowed_count == 1

    # 其余应该被拒绝
    denied_results = [r for r in results if not r.allowed]
    assert len(denied_results) == 4
    for r in denied_results:
        assert r.remaining_seconds > 0


@pytest.mark.asyncio
async def test_debounce_remaining_time_accuracy(redis_mgr: AsyncRedisManager) -> None:
    """测试剩余时间的准确性"""
    key = "test:debounce:time_accuracy"
    _ = await redis_mgr.op_prefixed.delete(key)

    # 设置 5 秒防抖
    result1 = await redis_mgr.op_prefixed.debounce_check_and_set(key, window_seconds=5)
    assert result1.allowed is True

    # 立即检查剩余时间
    result2 = await redis_mgr.op_prefixed.debounce_get_remaining(key)
    assert result2.allowed is False
    assert 4.0 <= result2.remaining_seconds <= 5.0

    # 等待 2 秒
    await asyncio.sleep(2)

    # 再次检查剩余时间
    result3 = await redis_mgr.op_prefixed.debounce_get_remaining(key)
    assert result3.allowed is False
    assert 2.0 <= result3.remaining_seconds <= 3.5


@pytest.mark.asyncio
async def test_debounce_custom_value(redis_mgr: AsyncRedisManager) -> None:
    """测试自定义存储值"""
    key = "test:debounce:custom_value"
    _ = await redis_mgr.op_prefixed.delete(key)

    custom_value = "my_custom_marker"
    result = await redis_mgr.op_prefixed.debounce_check_and_set(key, window_seconds=10, value=custom_value)
    assert result.allowed is True

    # 验证值确实被存储
    stored_value = await redis_mgr.op_prefixed.get(key)
    assert stored_value == custom_value


@pytest.mark.asyncio
async def test_simple_distributed_lock_acquired_success(redis_mgr: AsyncRedisManager) -> None:
    """测试成功获取锁并正常释放(修复Redis返回值判断)"""
    lock_key = f"test:sdl_success_lock:{uuid.uuid4().hex[:8]}"
    timeout = 10

    # 确保测试前无残留锁(Redis exists返回0表示不存在)
    pre_exists = await redis_mgr.op_prefixed.exists(lock_key)
    assert pre_exists == 0, "测试前锁应不存在"  # 修正:用==0判断

    # 第一次获取锁
    async with redis_mgr.op_prefixed.simple_distributed_lock(lock_key, timeout) as acquired:
        assert acquired is True, "首次获取锁应成功"

        # 验证锁已存储(exists返回1表示存在)
        lock_exists = await redis_mgr.op_prefixed.exists(lock_key)
        assert lock_exists == 1, "锁应被正确创建"

        lock_value = await redis_mgr.op_prefixed.get(lock_key)
        assert lock_value == "1", "锁的值应为'1'"

        ttl = await redis_mgr.op_prefixed.ttl(lock_key)
        assert 0 < ttl <= timeout, "锁超时时间不正确"

    # 退出上下文后验证锁已释放(exists返回0)
    post_exists = await redis_mgr.op_prefixed.exists(lock_key)
    assert post_exists == 0, "退出上下文后锁应被删除"  # 修正:用==0判断


@pytest.mark.asyncio
async def test_simple_distributed_lock_acquired_failed(redis_mgr: AsyncRedisManager) -> None:
    """测试锁被占用时获取失败(修复Redis返回值判断)"""
    lock_key = f"test:sdl_failed_lock:{uuid.uuid4().hex[:8]}"
    timeout = 10

    # 提前手动占用锁(模拟其他进程)
    set_ok = await redis_mgr.op_prefixed.set(lock_key, "1", expire=timeout, nx=True)
    assert set_ok is True, "提前占用锁失败"  # 假设set方法返回布尔值

    # 尝试获取已被占用的锁
    async with redis_mgr.op_prefixed.simple_distributed_lock(lock_key, timeout) as acquired:
        assert acquired is False, "锁被占用时应获取失败"

    # 验证锁仍被占用(exists返回1表示存在)
    still_exists = await redis_mgr.op_prefixed.exists(lock_key)
    assert still_exists == 1, "被占用的锁不应被当前进程释放"  # 修正:用==1判断

    # 清理测试数据
    await redis_mgr.op_prefixed.delete(lock_key)


@pytest.mark.asyncio
async def test_simple_distributed_lock_concurrent_acquire(redis_mgr: AsyncRedisManager) -> None:
    """测试并发场景下锁的唯一性(修复Redis返回值判断)"""
    lock_key = f"test:sdl_concurrent_lock:{uuid.uuid4().hex[:8]}"
    timeout = 10
    task_count = 5

    # 清理残留锁
    await redis_mgr.op_prefixed.delete(lock_key)

    # 并发任务:获取锁并返回结果
    async def task() -> bool:
        async with redis_mgr.op_prefixed.simple_distributed_lock(lock_key, timeout) as acquired:
            if acquired:
                await asyncio.sleep(0.5)  # 延长持有时间,确保并发冲突
            return acquired

    # 执行并发任务
    results: list[bool] = await asyncio.gather(*[task() for _ in range(task_count)])

    # 验证只有一个任务成功获取锁
    assert results.count(True) == 1, "并发场景下应只有一个任务获取锁"
    assert results.count(False) == task_count - 1, "其余任务应获取失败"

    # 验证所有任务完成后锁已释放(exists返回0)
    final_exists = await redis_mgr.op_prefixed.exists(lock_key)
    assert final_exists == 0, "所有任务完成后锁应被释放"  # 修正:用==0判断


@pytest.mark.asyncio
async def test_simple_distributed_lock_expire_reacquire(redis_mgr: AsyncRedisManager) -> None:
    """测试锁超时后可重新获取(补充Redis返回值判断)"""
    lock_key = f"test:sdl_expire_lock:{uuid.uuid4().hex[:8]}"
    short_timeout = 1

    # 第一次获取锁
    async with redis_mgr.op_prefixed.simple_distributed_lock(lock_key, short_timeout) as acquired1:
        assert acquired1 is True, "第一次应成功获取锁"
        assert await redis_mgr.op_prefixed.exists(lock_key) == 1, "锁应存在"

    # 等待锁超时
    await asyncio.sleep(short_timeout + 0.5)

    # 超时后锁应自动释放(exists返回0)
    assert await redis_mgr.op_prefixed.exists(lock_key) == 0, "超时后锁应自动释放"

    # 超时后重新获取
    async with redis_mgr.op_prefixed.simple_distributed_lock(lock_key, short_timeout) as acquired2:
        assert acquired2 is True, "超时后应能重新获取锁"

    # 清理
    await redis_mgr.op_prefixed.delete(lock_key)
