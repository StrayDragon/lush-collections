# lush-pydanticx

Pydantic v2 的一些小扩展. 这里不做“框架”,只收一些重复出现、但又不值得单独开一个包的函数/类型.

## 例子

把 `Json[T]` 字段在序列化时转成 `bytes`:

```python
from typing import Any

from pydantic import BaseModel, Json, field_serializer

from lush_pydanticx import json_to_bytes_serializer


class Payload(BaseModel):
    data: Json[dict[str, Any]]

    @field_serializer("data")
    def _ser(self, value: Any) -> bytes:
        return json_to_bytes_serializer(value)
```

## 开发

```bash
uv sync -p 3.10 --frozen
uv run -p 3.10 pytest
```
