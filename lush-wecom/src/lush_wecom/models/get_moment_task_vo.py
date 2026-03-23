"""
获取客户朋友圈企业发表成员任务模型
"""

from typing import Annotated, Literal

from pydantic import Field

from .common_vo import WeComApiModelBase, WeComBaseResp


class GetMomentTaskRequest(WeComApiModelBase):
    moment_id: str
    cursor: str | None = None
    limit: Annotated[int | None, Field(le=1000)] = 500


class GetMomentTaskItem(WeComApiModelBase):
    userid: str
    publish_status: Literal[0, 1]


class GetMomentTaskResponse(WeComBaseResp):
    next_cursor: str | None = None
    task_list: list[GetMomentTaskItem] = Field(default_factory=list)
