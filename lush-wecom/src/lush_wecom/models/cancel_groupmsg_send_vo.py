"""
企业微信停止群发相关模型
"""

from .common_vo import WeComApiModelBase, WeComBaseResp


class CancelGroupMsgSendRequest(WeComApiModelBase):
    msgid: str


class CancelGroupMsgSendResponse(WeComBaseResp):
    """停止企业群发响应"""
