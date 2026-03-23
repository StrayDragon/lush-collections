# lush-stdx

一些我经常复用的标准库小工具. 没有大而全的野心,只要它们还能保持“小”,就放这里.

## 例子

```python
from lush_stdx.langx import OptionT
from lush_stdx.urllibx import url_update_params

box = OptionT("hello")
assert box.unwrap() == "hello"

url = url_update_params("https://example.com?a=1", {"b": "2"})
assert url == "https://example.com?a=1&b=2"
```

## 开发

```bash
uv sync -p 3.10 --frozen
uv run -p 3.10 pytest
```
