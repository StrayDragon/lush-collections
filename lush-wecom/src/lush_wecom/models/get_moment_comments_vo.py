"""
获取客户朋友圈互动数据模型
"""

from pydantic import Field

from .common_vo import WeComApiModelBase, WeComBaseResp


class GetMomentCommentsRequest(WeComApiModelBase):
    moment_id: str
    userid: str


class GetMomentCommentsItem(WeComApiModelBase):
    external_userid: str | None = None
    userid: str | None = None
    create_time: int


class GetMomentCommentsResponse(WeComBaseResp):
    comment_list: list[GetMomentCommentsItem] = Field(default_factory=list)
    like_list: list[GetMomentCommentsItem] = Field(default_factory=list)
