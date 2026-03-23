"""
获取企业全部客户朋友圈列表模型
"""

import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, Field

from .common_vo import WeComApiModelBase, WeComBaseResp


def _dt_to_ts(value: datetime.datetime | int) -> int:
    if isinstance(value, int):
        return value
    return int(value.timestamp())


class GetMomentListText(WeComApiModelBase):
    content: str


class GetMomentListImage(WeComApiModelBase):
    media_id: str


class GetMomentListVideo(WeComApiModelBase):
    media_id: str
    thumb_media_id: str | None = None


class GetMomentListLink(WeComApiModelBase):
    title: str
    url: str


class GetMomentListLocation(WeComApiModelBase):
    latitude: str
    longitude: str
    name: str


class GetMomentListItem(WeComApiModelBase):
    moment_id: str
    creator: str | None = None
    create_time: int
    create_type: Literal[0, 1]
    visible_type: Literal[0, 1]
    text: GetMomentListText | None = None
    image: list[GetMomentListImage] | None = None
    video: GetMomentListVideo | None = None
    link: GetMomentListLink | None = None
    location: GetMomentListLocation | None = None


class GetMomentListRequest(WeComApiModelBase):
    start_time: Annotated[datetime.datetime | int, AfterValidator(_dt_to_ts)]
    end_time: Annotated[datetime.datetime | int, AfterValidator(_dt_to_ts)]
    creator: str | None = None

    filter_type: Literal[0, 1, 2] | None = None
    """
    0:企业发表
    1:个人发表
    2:所有

    最好设置这个为0, 有的时候默认不给或者设置为2都没有内容, 但是设置为0就有
    """

    cursor: str | None = None
    limit: Annotated[int | None, Field(le=20)] = 20


class GetMomentListResponse(WeComBaseResp):
    next_cursor: str | None = None
    moment_list: list[GetMomentListItem] = Field(default_factory=list)
