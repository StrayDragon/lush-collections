"""
企业微信提醒群发相关模型
"""

from .common_vo import WeComApiModelBase, WeComBaseResp


class RemindGroupMsgSendRequest(WeComApiModelBase):
    msgid: str


class RemindGroupMsgSendResponse(WeComBaseResp):
    """提醒企业群发响应"""
