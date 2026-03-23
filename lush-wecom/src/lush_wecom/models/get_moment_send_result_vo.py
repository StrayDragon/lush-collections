"""
获取客户朋友圈发送结果模型
"""

from typing import Annotated

from pydantic import Field

from .common_vo import WeComApiModelBase, WeComBaseResp


class GetMomentSendResultRequest(WeComApiModelBase):
    moment_id: str
    userid: str
    cursor: str | None = None
    limit: Annotated[int | None, Field(le=5000)] = 3000


class GetMomentSendResultItem(WeComApiModelBase):
    external_userid: str


class GetMomentSendResultResponse(WeComBaseResp):
    next_cursor: str | None = None
    customer_list: list[GetMomentSendResultItem] = Field(default_factory=list)
