# lush-wecom 贡献指南

请先了解下这个项目的基本情况, 见 [README](./README.md)

## 新增 API 开发范式

### 1. 命名规范

#### 文件命名模式

##### 视图对象(VO)模块

根据企微自己官方提供的文档, 优先使用api提供的名称, 如果冲突在考虑命名为
```
[功能领域]_[具体功能]_vo.py
```

示例:
- `send_app_message_vo.py` - 发送应用消息
- `get_groupmsg_list_vo.py` - 获取群发消息列表
- `add_moment_task_vo.py` - 创建朋友圈任务
- `auth_get_user_info_vo.py` - 网页授权获取用户信息

- 模型和类型命名
```python
# 请求模型
[Action] + [Resource] + Request     # SendAppMessageRequest
# 响应模型
[Action] + [Resource] + Response    # SendAppMessageResponse
# 内容模型
[Type] + Content                    # TextContent, ImageContent
# 列表项模型
[Resource] + Item                   # TaskItem
# 特殊业务对象
[Business] + [Type]                 # TemplateCardContent
```

- 客户端方法命名
```python
# RESTful 风格的动词
async def send_app_message(...)      # 发送消息
async def get_groupmsg_list(...)     # 获取列表
async def add_msg_template(...)      # 创建模板
async def cancel_moment_task(...)    # 取消任务
async def upload_temporary_media(...) # 上传媒体
```

### 2. 数据模型设计规范

#### 基础模型继承
```python
from pydantic import Field
from .common_vo import WeComApiModelBase, WeComBaseResp

class YourRequest(WeComApiModelBase):
    """请求模型 - 继承 WeComApiModelBase"""

class YourResponse(WeComBaseResp):
    """响应模型 - 继承 WeComBaseResp"""
```

#### 字段定义模式
```python
from typing import Annotated, Literal

class TextContent(WeComApiModelBase):
    """文本消息内容"""
    ...


# 优先使用 Annotated 组合类型和描述
msgtype: Annotated[
    Literal["text", "image", "voice", "video"],
    Field(description="消息类型")
] = "text"

safe: Annotated[
    Literal[0, 1, 2] | None,
    Field(description="表示是否是保密消息")
] = None

# 除非必要的 Field参数比如 default_factory, default 自定义对象等无法使用 Annotated模式
items: list[int] | None = Field(default_factory=list,description="列表")

items: Item = Field(default=Item,description="列表")
```

可以混用两种模式 pydantic 自动处理

### 3. 客户端方法实现规范

#### 标准方法结构
```python
async def your_api_method(
    self,
    payload: YourRequest
) -> YourResponse:
    """
    API方法简短描述
    参考文档: https://developer.work.weixin.qq.com/document/path/XXXXX
    """
    endpoint = "/api/endpoint"
    json_payload = payload.model_dump(exclude_none=True)
    return await self._make_request("POST", endpoint, YourResponse, json=json_payload)
```

#### 文件处理方法规范
```python
async def upload_temporary_media(self, file_path: str, media_type: str) -> TemporaryMediaResponse:
    """
    上传临时素材文件到企业微信
    参考文档: https://developer.work.weixin.qq.com/document/path/XXXXX
    """
    # 1. 文件验证
    path = anyio.Path(file_path)
    if not await path.exists():
        raise FileNotFoundError(f"文件未找到: {file_path}")

    # 2. 大小和类型检查
    file_stat = await path.stat()
    if file_stat.st_size <= 5:
        raise ValueError("文件大小必须大于5个字节")

    # 3. 媒体类型验证
    valid_types = ["image", "voice", "video", "file"]
    if media_type not in valid_types:
        raise ValueError(f"无效的 media_type '{media_type}'必须是 {valid_types} 中的一个")

    # 4. 构建请求
    endpoint = "/media/upload"
    params = {"type": media_type}
    data = await path.read_bytes()
    files = {"media": (SyncPath(file_path).name, data)}

    return await self._make_request("POST", endpoint, TemporaryMediaResponse, params=params, files=files)
```

#### 流式下载方法规范
```python
async def get_temporary_media_with_range(
    self,
    media_id: str,
    start_byte: int = 0,
    end_byte: int | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> AsyncIterator[bytes]:
    """
    根据media_id获取临时素材文件(支持断点下载)

    Args:
        media_id: 媒体文件ID
        start_byte: 起始字节位置
        end_byte: 结束字节位置,None表示到文件末尾
        chunk_size: 分块大小,默认20MB

    Returns:
        文件流迭代器

    Example:
        # 下载文件的前1024字节
        stream = client.get_temporary_media_with_range("MEDIA_ID", 0, 1023)

    参考文档: https://developer.work.weixin.qq.com/document/path/XXXXX
    """
    range_header = f"bytes={start_byte}-{end_byte}" if end_byte is not None else f"bytes={start_byte}-"
    return self._make_stream_request(
        method="GET",
        endpoint="/media/get",
        chunk_size=chunk_size,
        range_header=range_header,
        params={"media_id": media_id},
    )
```

### 4. 错误处理规范

#### 参数验证
```python
def _validate_upload_params(self, file_path: str, media_type: str) -> None:
    """验证上传参数"""
    # 文件路径验证
    if not file_path or not isinstance(file_path, str):
        raise ValueError("file_path 必须是有效的字符串路径")

    # 媒体类型验证
    valid_types = ["image", "voice", "video", "file"]
    if media_type not in valid_types:
        raise ValueError(f"无效的 media_type '{media_type}'必须是 {valid_types} 中的一个")

def _check_file_size(self, file_size: int, max_size: int) -> None:
    """检查文件大小"""
    if file_size <= 5:
        raise ValueError("文件大小必须大于5个字节")
    if file_size > max_size:
        max_size_mb = max_size // (1024 * 1024)
        raise ValueError(f"文件大小不能超过 {max_size_mb}MB")
```

#### 资源清理
```python
async def upload_temporary_media_from_url(self, media_url: str, media_type: str) -> TemporaryMediaResponse:
    """从URL下载并上传媒体文件"""
    temp_path: str | None = None
    try:
        # 下载文件
        download_result = await self._download_media_from_url(media_url)
        temp_path = download_result.temp_file_path

        # 处理业务逻辑
        return await self.upload_temporary_media(temp_path, media_type)
    finally:
        # 确保临时文件被清理
        if temp_path:
            p = anyio.Path(temp_path)
            with contextlib.suppress(Exception):
                await p.unlink(missing_ok=True)
```

### 5. 文档字符串规范

#### 完整的文档格式
```python
def get_failure_reason_when_send_only_one_user(self) -> str:
    """
    获取单个用户发送失败的原因

    当发送消息给单个用户时,如果发送失败,此方法可以提供具体的失败原因.

    Returns:
        str: 失败原因描述,如果发送成功则返回空字符串

        可能的返回值:
        - "不合法的userid(已统一lowercase): xxx"
        - "没有基础接口许可(包含已过期)的userid: xxx"
        - ""

    Note:
        - 仅适用于发送给单个用户的情况
        - 返回的错误信息已经过统一处理和格式化
    """
    if self.invaliduser:
        return f"不合法的userid(已统一lowercase): {self.invaliduser}"
    if self.unlicenseduser:
        return f"没有基础接口许可(包含已过期)的userid: {self.unlicenseduser}"
    return ""
```

#### 内联注释规范
```python
async def complex_api_method(self, payload: ComplexRequest) -> ComplexResponse:
    """复杂API方法的注释示例"""

    # 1. 参数预处理
    # NOTE: 确保所有可选字段都被正确处理
    processed_payload = payload.model_dump(exclude_none=True)

    # 2. 构建API端点
    # TODO: 后续考虑将端点配置化
    endpoint = "/externalcontact/complex_operation"

    # 3. 特殊字段处理
    # HACK: 临时解决方案,需要后续重构
    if payload.special_field:
        processed_payload["special_field"] = self._format_special_field(payload.special_field)

    # 4. 发起请求
    # WARNING: 此处需要特别注意超时处理
    return await self._make_request(
        "POST",
        endpoint,
        ComplexResponse,
        json=processed_payload,
        timeout=30  # 增加超时时间
    )
```

### 6. 同步/异步版本一致性

#### API接口对齐
```python
# 同步版本 (_sync/__init__.py)
def send_app_message(self, payload: send_app_message_vo.SendAppMessageRequest) -> send_app_message_vo.SendAppMessageResponse:
    """发送应用消息 - 同步版本"""
    endpoint = "/message/send"
    json_payload = payload.model_dump(exclude_none=True)
    return self._make_request("POST", endpoint, send_app_message_vo.SendAppMessageResponse, json=json_payload)

# 异步版本 (_async/__init__.py)
async def send_app_message(self, payload: send_app_message_vo.SendAppMessageRequest) -> send_app_message_vo.SendAppMessageResponse:
    """发送应用消息 - 异步版本"""
    endpoint = "/message/send"
    json_payload = payload.model_dump(exclude_none=True)
    return await self._make_request("POST", endpoint, send_app_message_vo.SendAppMessageResponse, json=json_payload)
```

#### 文档字符串同步
```python
# 使用脚本自动同步文档字符串
# client/__script_docstring_sync_to_async.py
# 确保 sync 和 async 版本的文档保持一致
```

### 7. 示例与笔记

如果你想补充脚本或 ipynb 示例,请同时补齐对应的文档说明与最小可跑的测试用例.
示例里不要提交真实的 corp_id / corp_secret、用户数据、内部域名/IP 等内容.


## 代码质量要求

###  代码风格
- 使用 `ruff` 进行代码检查和格式化


###  异常处理
- 使用项目定义的异常类
- 提供清晰的错误信息
- 合理使用日志记录
- 确保资源正确清理

### 性能考虑
- 避免不必要的内存占用
- 使用流式处理大文件
- 合理设置超时时间
- 实现适当的缓存策略

## 最佳实践总结

### 1. 设计原则
- **一致性**: 与现有API保持一致的命名和结构
- **可扩展性**: 设计时考虑未来的功能扩展
- **易用性**: 提供直观的接口和清晰的错误信息
- **健壮性**: 全面的参数验证和错误处理

### 2. 文档优先
- 在编写代码前先写好文档字符串
- 提供详细的使用示例
- 包含完整的参数说明和返回值描述
- 添加相关的企业微信API文档链接

如有疑问,请查看项目的现有API实现或联系项目维护者.
