# lush-sqlalchemyx

SQLAlchemy(偏 asyncio) 的一组工具和封装. 这里的东西偏“工程向”: 解决常见的 session 管理、只读会话、以及一些重复写到吐的样板代码.

## 例子

一个最小的异步 MySQL 管理器:

```python
import asyncio

from lush_sqlalchemyx.mgrs.mysql.manager import AsyncMySQLManager

async def main() -> None:
    mgr = AsyncMySQLManager("mysql+aiomysql://<user>:<password>@127.0.0.1:3306/<dbname>")
    ok = await mgr.health_check()
    print(ok)

    await mgr.close()


asyncio.run(main())
```

## 开发

```bash
uv sync -p 3.10 --frozen
uv run -p 3.10 pytest
```
