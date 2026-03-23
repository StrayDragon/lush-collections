"""
企业微信获取群发成员执行结果相关模型
"""

from pydantic import Field

from .common_vo import WeComApiModelBase, WeComBaseResp

MAX_LIMIT = 1000


class GetGroupMsgSendResultRequest(WeComApiModelBase):
    msgid: str
    userid: str
    limit: int | None = MAX_LIMIT
    cursor: str | None = None


class SendResultItem(WeComApiModelBase):
    external_userid: str | None = None
    chat_id: str | None = None
    userid: str
    status: int
    send_time: int | None = None


class GetGroupMsgSendResultResponse(WeComBaseResp):
    next_cursor: str | None = None
    send_list: list[SendResultItem] = Field(default_factory=list)
