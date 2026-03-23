# lush-wecom

WeCom(企业微信) 的客户端封装与数据模型. 目标是让你少写一点“拼 URL + 拼 params + 手动处理 errcode”的重复代码.

它提供:

- 同步/异步两套客户端
- access_token 管理(可接 Redis 或自定义存储)
- 统一的异常与重试策略
- pydantic v2 的请求/响应模型

## 快速开始

```python
from lush_wecom import WeComClient, WeComTokenManager
from lush_wecom.models.send_app_message_vo import SendAppMessageRequest, TextContent

token_mgr = WeComTokenManager(corpid="YOUR_CORP_ID", corpsecret="YOUR_CORP_SECRET")
client = WeComClient(token_manager=token_mgr)

req = SendAppMessageRequest(
    touser="userid1|userid2",
    agentid=1000002,
    msgtype="text",
    text=TextContent(content="hello"),
)
resp = client.send_app_message(req)
```

## 开发

```bash
uv sync -p 3.10 --frozen
uv run -p 3.10 pytest
```

## 目录结构

```
src/lush_wecom/
├── __init__.py           # 包导出
├── client/               # 客户端实现
│   ├── __init__.py       # 客户端统一导出
│   ├── _async/           # 异步客户端实现
│   └── _sync/            # 同步客户端实现
├── core/                 # 核心功能
│   ├── base.py           # 基础客户端类
│   ├── const.py          # 常量定义
│   ├── exceptions.py     # 异常定义
│   ├── storage.py        # 存储抽象
│   └── token_mgr.py      # Token管理器
├── models/               # 数据模型
│   ├── common_vo.py      # 通用模型
│   ├── *_vo.py           # 各API专用模型
├── utils/                # 工具函数
│   ├── retry.py          # 重试工具
│   └── oauth.py          # OAuth工具
└── tests/                # 测试代码
```
