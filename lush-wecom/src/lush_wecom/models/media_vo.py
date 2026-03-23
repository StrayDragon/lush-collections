"""
媒体通用模型
"""

from pydantic import Field

from .common_vo import WeComApiModelBase


class MediaDownloadResult(WeComApiModelBase):
    """媒体文件下载结果模型"""

    temp_file_path: str = Field(description="临时文件路径")
    filename: str = Field(description="文件名")
    content_type: str = Field(description="MIME类型")
    file_size: int = Field(description="文件大小(字节)")
