# lush-redisx

基于 `redis`(redis-py) asyncio 的一层薄封装: 连接池、key 前缀、以及一些常用的小模式(缓存/防抖/节流).

## 例子

```python
import asyncio

from lush_redisx import AsyncRedisManager

async def main() -> None:
    redis_mgr = AsyncRedisManager(host="localhost", port=6379, db=0, key_prefix="demo")

    # set/get 会自动加前缀,避免不同业务互相踩 key
    await redis_mgr.op_prefixed.set("foo", {"bar": 1})
    value = await redis_mgr.op_prefixed.get("foo")
    print(value)

    await redis_mgr.close()


asyncio.run(main())
```

## 开发

```bash
uv sync -p 3.10 --frozen
uv run -p 3.10 pytest
```
