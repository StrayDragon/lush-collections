"""
企业微信获取群发成员发送任务列表相关模型
"""

from enum import IntEnum

from pydantic import Field

from .common_vo import WeComApiModelBase, WeComBaseResp


class GetGroupMsgTaskRequest(WeComApiModelBase):
    msgid: str
    limit: int | None = 1000
    cursor: str | None = None


class TaskItem(WeComApiModelBase):
    userid: str
    status: int = Field(..., description="发送状态: 0-未发送 2-已发送")
    send_time: int | None = Field(None, description="发送时间,未发送时不返回")


class GetGroupMsgTaskResponse(WeComBaseResp):
    next_cursor: str | None = None
    task_list: list[TaskItem] = Field(default_factory=list)


class TaskItemStatus(IntEnum):
    NOT_SEND = 0
    SENT = 2
