# lush-fastapix

一个小型 FastAPI 增强包. 主要目标很简单: 让生成出来的 OpenAPI schema 更“像人写的”,尤其是枚举/参数的展示.

最常用的是 `FastAPIX`. 它继承自 `fastapi.FastAPI`,覆写 `openapi()` 并在 schema 生成后调用 `enhance_openapi_schema()`.

## 快速开始

```python
from lush_fastapix import FastAPIX

app = FastAPIX(title="demo", version="0.1.0")
```

## 开发

```bash
uv sync -p 3.10 --frozen
uv run -p 3.10 pytest
```
