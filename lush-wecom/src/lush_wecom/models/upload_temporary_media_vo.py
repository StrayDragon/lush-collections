"""
上传临时素材 API 模型
"""

from pydantic import Field

from .common_vo import WeComBaseResp


class UploadTemporaryMediaResponse(WeComBaseResp):
    """上传临时素材响应模型"""

    media_type: str = Field(..., alias="type")
    media_id: str
    created_at: str
