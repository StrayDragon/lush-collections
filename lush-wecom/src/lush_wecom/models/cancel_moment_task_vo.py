"""
停止客户朋友圈任务模型
"""

from .common_vo import WeComApiModelBase, WeComBaseResp


class CancelMomentTaskRequest(WeComApiModelBase):
    moment_id: str


class CancelMomentTaskResponse(WeComBaseResp):
    """停止客户朋友圈任务响应"""
