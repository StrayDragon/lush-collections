"""测试 AsyncRedisManager 的异常处理和边界情况"""  # noqa: INP001

from collections import abc
from datetime import timedelta

import pytest
from redis.exceptions import RedisError

from lush_redisx import AsyncRedisManager, AsyncRedisPrefixedOp, SerializationMode


class FakeRedisWithExceptions:
    """模拟 Redis,支持触发异常"""

    def __init__(self, *, exceptions: dict[str, Exception] | None = None) -> None:
        self.store: dict[str, object] = {}
        self._exceptions: dict[str, Exception] = exceptions or {}

    def _raise_if_needed(self, method: str) -> None:
        exc = self._exceptions.get(method)
        if exc is not None:
            raise exc

    async def get(self, key: str) -> object | None:
        self._raise_if_needed("get")
        return self.store.get(key)

    async def set(  # noqa: A003
        self,
        key: str,
        value: str,
        *,
        ex: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        self._raise_if_needed("set")
        exists = key in self.store
        if nx and exists:
            return False
        if xx and not exists:
            return False
        self.store[key] = value
        return True

    async def delete(self, *keys: str) -> int:
        self._raise_if_needed("delete")
        deleted = 0
        for key in keys:
            if key in self.store:
                deleted += 1
                del self.store[key]
        return deleted

    async def exists(self, *keys: str) -> int:
        self._raise_if_needed("exists")
        return sum(1 for k in keys if k in self.store)

    async def ttl(self, key: str) -> int:
        self._raise_if_needed("ttl")
        if key not in self.store:
            return -2
        return -1

    async def expire(self, key: str, seconds: int) -> bool:
        self._raise_if_needed("expire")
        return True

    async def hget(self, key: str, field: str) -> str | None:
        self._raise_if_needed("hget")
        return None

    async def hset(self, key: str, field: str, value: str) -> int:
        self._raise_if_needed("hset")
        return 1

    async def hgetall(self, key: str) -> dict[str, str]:
        self._raise_if_needed("hgetall")
        return {}

    async def lpush(self, key: str, *values: str) -> int:
        self._raise_if_needed("lpush")
        return len(values)

    async def rpush(self, key: str, *values: str) -> int:
        self._raise_if_needed("rpush")
        return len(values)

    async def lpop(self, key: str, count: int | None = None) -> str | None:
        self._raise_if_needed("lpop")
        return None

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        self._raise_if_needed("lrange")
        return []

    async def sadd(self, key: str, *values: str) -> int:
        self._raise_if_needed("sadd")
        return len(values)

    async def smembers(self, key: str) -> abc.Set[str]:
        self._raise_if_needed("smembers")
        return set[str]()

    async def mget(self, *keys: str) -> list[str | None]:
        self._raise_if_needed("mget")
        return [self.store.get(k) for k in keys]  # type: ignore[return-value]

    async def mset(self, mapping: dict[str, str]) -> bool:
        self._raise_if_needed("mset")
        self.store.update(mapping)
        return True

    async def ping(self) -> str:
        self._raise_if_needed("ping")
        return "PONG"

    async def aclose(self, close_connection_pool: bool = False) -> None:
        self._raise_if_needed("aclose")


class TestAsyncRedisPrefixedOpEdgeCases:
    """测试 AsyncRedisPrefixedOp 的边界情况和异常处理"""

    def test_apply_prefix_empty_key_prefix(self) -> None:
        """测试空 key_prefix 时 _apply_prefix 返回原键"""
        from lush_redisx.async_redis import _apply_prefix

        assert _apply_prefix("mykey", "") == "mykey"

    def test_batch_apply_prefix_empty_key_prefix(self) -> None:
        """测试空 key_prefix 时 _batch_apply_prefix 返回原键列表"""
        from lush_redisx.async_redis import _batch_apply_prefix

        result = _batch_apply_prefix(["key1", "key2"], "")
        assert result == ["key1", "key2"]

    def test_get_real_key_method(self) -> None:
        """测试 get_real_key 方法"""
        fake_redis = FakeRedisWithExceptions()
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")
        real_key = op.get_real_key("mykey")
        assert real_key == ":test:mykey"

    def test_get_real_key_empty_prefix(self) -> None:
        """测试空前缀时的 get_real_key 方法"""
        fake_redis = FakeRedisWithExceptions()
        op = AsyncRedisPrefixedOp(fake_redis, "")
        real_key = op.get_real_key("mykey")
        assert real_key == "mykey"


class TestSerializationModes:
    """测试不同的序列化模式"""

    @pytest.mark.asyncio
    async def test_serialize_string_mode(self) -> None:
        """测试 STRING 序列化模式"""
        fake_redis = FakeRedisWithExceptions()
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        # 测试 STRING 模式序列化
        result = op._serialize(123, SerializationMode.STRING)
        assert result == "123"

        result = op._serialize({"a": 1}, SerializationMode.STRING)
        assert result == "{'a': 1}"

    @pytest.mark.asyncio
    async def test_serialize_none_mode(self) -> None:
        """测试 NONE 序列化模式"""
        fake_redis = FakeRedisWithExceptions()
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        result = op._serialize("value", SerializationMode.NONE)
        assert result == "value"

    @pytest.mark.asyncio
    async def test_deserialize_bytes_to_json(self) -> None:
        """测试 bytes 值的反序列化"""
        fake_redis = FakeRedisWithExceptions()
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        # bytes 值应该被解码
        result = op._deserialize(b'{"key": "value"}', SerializationMode.JSON)
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_deserialize_non_json_string(self) -> None:
        """测试非 JSON 字符串的反序列化"""
        fake_redis = FakeRedisWithExceptions()
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        # 当 JSON 解析失败时返回原值
        result = op._deserialize("not valid json", SerializationMode.JSON)
        assert result == "not valid json"

    @pytest.mark.asyncio
    async def test_deserialize_none_value(self) -> None:
        """测试 None 值的反序列化"""
        fake_redis = FakeRedisWithExceptions()
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        result = op._deserialize(None, SerializationMode.JSON)
        assert result is None

    @pytest.mark.asyncio
    async def test_deserialize_other_type(self) -> None:
        """测试其他类型的值转换为字符串"""
        fake_redis = FakeRedisWithExceptions()
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        result = op._deserialize(123, SerializationMode.NONE)
        assert result == "123"


class TestExceptionHandling:
    """测试 Redis 异常处理"""

    @pytest.mark.asyncio
    async def test_get_with_redis_error(self) -> None:
        """测试 get 方法的异常处理"""
        fake_redis = FakeRedisWithExceptions(exceptions={"get": RedisError("Simulated Redis error")})
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        result = await op.get("key", default="fallback")
        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_set_with_redis_error(self) -> None:
        """测试 set 方法的异常处理"""
        fake_redis = FakeRedisWithExceptions(exceptions={"set": RedisError("Simulated Redis error")})
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        result = await op.set("key", "value", expire=60)
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_with_redis_error(self) -> None:
        """测试 delete 方法的异常处理"""
        fake_redis = FakeRedisWithExceptions(exceptions={"delete": RedisError("Error")})
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        result = await op.delete("key")
        assert result == 0

    @pytest.mark.asyncio
    async def test_exists_with_redis_error(self) -> None:
        """测试 exists 方法的异常处理"""
        fake_redis = FakeRedisWithExceptions(exceptions={"exists": RedisError("Error")})
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        result = await op.exists("key")
        assert result == 0

    @pytest.mark.asyncio
    async def test_expire_with_redis_error(self) -> None:
        """测试 expire 方法的异常处理"""
        fake_redis = FakeRedisWithExceptions(exceptions={"expire": RedisError("Error")})
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        result = await op.expire("key", 60)
        assert result is False

    @pytest.mark.asyncio
    async def test_ttl_with_redis_error(self) -> None:
        """测试 ttl 方法的异常处理"""
        fake_redis = FakeRedisWithExceptions(exceptions={"ttl": RedisError("Error")})
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        result = await op.ttl("key")
        assert result == -1

    @pytest.mark.asyncio
    async def test_throttle_check_and_set_with_redis_error(self) -> None:
        """测试 throttle_check_and_set 方法的异常处理"""
        fake_redis = FakeRedisWithExceptions(exceptions={"set": RedisError("Error")})
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        result = await op.throttle_check_and_set("key", window_seconds=60)
        # 异常时返回允许通过
        assert result.allowed is True
        assert result.redis_key == ":test:key"

    @pytest.mark.asyncio
    async def test_debounce_check_and_set_with_redis_error(self) -> None:
        """测试 debounce_check_and_set 方法的异常处理"""
        fake_redis = FakeRedisWithExceptions(exceptions={"set": RedisError("Error")})
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        result = await op.debounce_check_and_set("key", window_seconds=60)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_debounce_get_remaining_with_redis_error(self) -> None:
        """测试 debounce_get_remaining 方法的异常处理"""
        fake_redis = FakeRedisWithExceptions(exceptions={"exists": RedisError("Error")})
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        result = await op.debounce_get_remaining("key")
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_mget_with_redis_error(self) -> None:
        """测试 mget 方法的异常处理"""
        fake_redis = FakeRedisWithExceptions(exceptions={"mget": RedisError("Error")})
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        result = await op.mget("key1", "key2")
        assert result == [None, None]

    @pytest.mark.asyncio
    async def test_mset_with_redis_error(self) -> None:
        """测试 mset 方法的异常处理"""
        fake_redis = FakeRedisWithExceptions(exceptions={"mset": RedisError("Error")})
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        result = await op.mset({"key1": "value1"})
        assert result is False

    @pytest.mark.asyncio
    async def test_get_json_with_bytes(self) -> None:
        """测试 get_json 处理 bytes 值"""
        fake_redis = FakeRedisWithExceptions()
        fake_redis.store[":test:json_key"] = b'{"data": "test"}'
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        result = await op.get_json("json_key")
        assert result == {"data": "test"}


class TestSimpleDistributedLockException:
    """测试 simple_distributed_lock 的异常处理"""

    @pytest.mark.asyncio
    async def test_lock_release_exception(self) -> None:
        """测试锁释放时的异常处理"""
        fake_redis = FakeRedisWithExceptions(exceptions={"delete": Exception("Delete failed")})
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        async with op.simple_distributed_lock("lock", timeout=5) as acquired:
            assert acquired is True
        # 即使删除失败也不应该抛出异常

    @pytest.mark.asyncio
    async def test_lock_not_acquired(self) -> None:
        """测试锁未获取时的行为"""
        fake_redis = FakeRedisWithExceptions()
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        # 第一次获取锁
        async with op.simple_distributed_lock("lock", timeout=5) as acquired1:
            assert acquired1 is True

        # 锁已释放,第二次应该能获取成功
        async with op.simple_distributed_lock("lock", timeout=5) as acquired2:
            assert acquired2 is True


class TestAsyncRedisManagerEdgeCases:
    """测试 AsyncRedisManager 的边界情况"""

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self) -> None:
        """测试健康检查连接错误处理"""
        mgr = AsyncRedisManager(host="127.0.0.1", port=1, socket_connect_timeout=1, socket_timeout=1)
        try:
            result = await mgr.health_check()
            assert result is False
        finally:
            await mgr.close()

    @pytest.mark.asyncio
    async def test_hget_returns_default(self) -> None:
        """测试 hget 返回默认值"""
        fake_redis = FakeRedisWithExceptions()
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        result = await op.hget("key", "field", default="default_value")
        assert result == "default_value"


class TestGetJsonWithDifferentTypes:
    """测试 get_json 处理不同类型值"""

    @pytest.mark.asyncio
    async def test_get_json_returns_none_on_decode_error(self) -> None:
        """测试 get_json 处理 JSON 解码错误时返回 None"""
        fake_redis = FakeRedisWithExceptions()
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        fake_redis.store[":test:key"] = b"not valid json"
        result = await op.get_json("key")
        # JSON 解码错误时返回 None (default)
        assert result is None


class TestDebounceGetRemaining:
    """测试 debounce_get_remaining 方法"""

    @pytest.mark.asyncio
    async def test_debounce_get_remaining_key_not_exists(self) -> None:
        """测试键不存在时返回允许"""
        fake_redis = FakeRedisWithExceptions()
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        result = await op.debounce_get_remaining("nonexistent")
        assert result.allowed is True
        assert result.remaining_seconds == 0.0

    @pytest.mark.asyncio
    async def test_debounce_get_remaining_key_exists(self) -> None:
        """测试键存在时返回剩余时间"""
        fake_redis = FakeRedisWithExceptions()
        fake_redis.store[":test:existing"] = "1"
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        result = await op.debounce_get_remaining("existing")
        assert result.redis_key == ":test:existing"


class TestRemainingUncoveredLines:
    """测试剩余未覆盖的行"""

    @pytest.mark.asyncio
    async def test_set_with_timedelta_expire(self) -> None:
        """测试 set 方法使用 timedelta 类型的 expire 参数 (行 156)"""
        fake_redis = FakeRedisWithExceptions()
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        # 使用 timedelta 作为 expire 参数
        result = await op.set("key", "value", expire=timedelta(seconds=60))
        assert result is True
        # 验证键已设置
        assert ":test:key" in fake_redis.store

    @pytest.mark.asyncio
    async def test_get_json_with_invalid_json_string(self) -> None:
        """测试 get_json 处理无效 JSON 字符串 (行 415)"""
        fake_redis = FakeRedisWithExceptions()
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        # 设置无效的 JSON 字符串值
        fake_redis.store[":test:key"] = "not valid json at all"
        result = await op.get_json("key", default={})
        # 应该返回 default 因为无法解析为 JSON
        assert result == {}

    @pytest.mark.asyncio
    async def test_serialize_fallback_return(self) -> None:
        """测试 _serialize 方法的 fallback 返回 (行 620)"""
        fake_redis = FakeRedisWithExceptions()
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        # 测试一个不在任何模式中的值
        class CustomObject:
            pass

        obj = CustomObject()
        # 使用 NONE 模式但传入自定义对象应该返回原值
        result = op._serialize(obj, SerializationMode.NONE)
        assert result is obj

    @pytest.mark.asyncio
    async def test_get_json_returns_none_when_redis_returns_none(self) -> None:
        """测试 get_json 在 Redis 返回 None 时返回 default (行 410)"""
        fake_redis = FakeRedisWithExceptions()
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        # 不设置任何值,get 会返回 None
        result = await op.get_json("nonexistent_key", default="default_value")
        assert result == "default_value"

    @pytest.mark.asyncio
    async def test_get_json_with_non_string_bytes_value(self) -> None:
        """测试 get_json 处理非字符串类型的值 (行 415)"""
        fake_redis = FakeRedisWithExceptions()
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        # 创建一个无法被 JSON 解析的自定义对象
        class Unjsonable:
            def __str__(self):
                return "not json"

        # 这会触发: elif not isinstance(value, str): value = str(value)
        # 然后 json.loads 会失败,因为 "not json" 不是有效的 JSON
        fake_redis.store[":test:key"] = Unjsonable()
        result = await op.get_json("key", default="fallback")
        # 自定义对象被转换为字符串 "not json",不是有效 JSON,返回 default
        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_serialize_unknown_mode_fallback(self) -> None:
        """测试 _serialize 遇到未知 mode 时的 fallback (行 620)"""
        fake_redis = FakeRedisWithExceptions()
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        # 创建一个假的 SerializationMode 值
        class FakeMode:
            pass

        fake_mode = FakeMode()
        result = op._serialize("value", fake_mode)  # type: ignore[reportArgumentType]
        # 未知 mode 应该返回原值
        assert result == "value"

    @pytest.mark.asyncio
    async def test_deserialize_unknown_mode_fallback(self) -> None:
        """测试 _deserialize 遇到未知 mode 时的 fallback (行 640)"""
        fake_redis = FakeRedisWithExceptions()
        op = AsyncRedisPrefixedOp(fake_redis, ":test:")

        # 创建一个假的 SerializationMode 值
        class FakeMode:
            pass

        fake_mode = FakeMode()
        result = op._deserialize("value", fake_mode)  # type: ignore[reportArgumentType]
        # 未知 mode 应该返回原值
        assert result == "value"
