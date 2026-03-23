"""
上传图片 API 模型
"""

from .common_vo import WeComBaseResp


class UploadImageResponse(WeComBaseResp):
    """上传图片响应模型"""

    url: str
