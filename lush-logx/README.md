# lush-logx

structlog 的一套常用配置封装,顺手带了一个“解析结构化日志”的 CLI.

## 用法

最常见的场景是把项目日志统一成一套结构(开发环境友好,线上 JSON 稳定):

```python
from lush_logx import configure_logging_once, get_logger

configure_logging_once()
logger = get_logger(__name__)
logger.info("hello", foo="bar")
```

## CLI

`lush-logx` 内置了一个日志解析器,适合在本地把 JSON 日志流快速“读成”人能看的样子:

```bash
uv run lush-logx-cli-log-parser < your.log
```

## 开发

```bash
uv sync -p 3.10 --frozen
uv run -p 3.10 pytest
```
