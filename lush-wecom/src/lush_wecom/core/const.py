# Token相关错误码
from enum import IntEnum
from typing import Literal

TOKEN_INVALID_ERROR_CODES: set[int] = {40001, 40014, 42001, 41001}

# 可重试的错误码
RETRYABLE_ERROR_CODES: set[int] = {
    45009,  # 接口调用超过限制
    40001,  # access_token不合法
    40014,  # 不合法的access_token
    42001,  # access_token超时
    41001,  # 缺少access_token参数
    -1,  # 系统繁忙
}

# 文件大小限制(字节)
FILE_SIZE_LIMITS: dict[Literal["image", "voice", "video", "file", "upload_image"], int] = {
    "image": 10 * 1024 * 1024,  # 10MB
    "voice": 2 * 1024 * 1024,  # 2MB
    "video": 10 * 1024 * 1024,  # 10MB
    "file": 20 * 1024 * 1024,  # 20MB
    "upload_image": 2 * 1024 * 1024,  # 上传图片限制2MB
}

# 附件上传相关限制
# 参考: https://developer.work.weixin.qq.com/document/path/95098
AttachmentTypeLiteral = Literal[1, 2]
"""
1: 朋友圈, 2: 商品图册
"""

ATTACHMENT_FILE_SIZE_LIMITS: dict[Literal["image", "video", "file"], int] = {
    "image": 10 * 1024 * 1024,  # 10MB
    "video": 10 * 1024 * 1024,  # 10MB
    "file": 10 * 1024 * 1024,  # 10MB
}

ATTACHMENT_TYPE_MEDIA_LIMITS: dict[AttachmentTypeLiteral, tuple[Literal["image", "video", "file"], ...]] = {
    1: ("image", "video"),  # 朋友圈
    2: ("image",),  # 商品图册
}

# 朋友圈图片分辨率限制
# 参考: https://developer.work.weixin.qq.com/document/path/95098
# 朋友圈类型图片,长边不超过10800像素,短边不超过1080像素
MOMENT_IMAGE_MAX_LONG_EDGE = 10800  # 长边最大像素
MOMENT_IMAGE_MAX_SHORT_EDGE = 1080  # 短边最大像素
MOMENT_IMAGE_MIN_DIMENSION = 1  # 最小尺寸

# 默认配置
DEFAULT_TIMEOUT = 10
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 0.0
DEFAULT_CHUNK_SIZE = 20 * 1024 * 1024  # 20MB
TOKEN_CACHE_BUFFER_SECONDS = 10  # token缓存提前过期缓冲时间


class WeComAPIErrorCode(IntEnum):
    # errcode: 41093, errmsg: group message canceled
    GROUP_MESSAGE_CANCELED = 41093
