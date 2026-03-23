"""
上传附件资源 API 模型
"""

from pydantic import Field

from .common_vo import WeComBaseResp


class UploadAttachmentMediaResponse(WeComBaseResp):
    """上传附件资源的响应模型"""

    media_type: str = Field(..., alias="type")
    media_id: str
    created_at: int | None = None
