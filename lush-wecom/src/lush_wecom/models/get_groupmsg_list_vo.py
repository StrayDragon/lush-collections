"""
企业微信获取群发记录列表相关模型
"""

import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, Field

from .common_vo import WeComApiModelBase, WeComBaseResp


def dt_to_int_ts(dt: datetime.datetime) -> int:
    return int(dt.timestamp())


class TextMessage(WeComApiModelBase):
    content: str


class ImageAttachment(WeComApiModelBase):
    media_id: str | None = None
    pic_url: str | None = None


class LinkAttachment(WeComApiModelBase):
    title: str
    url: str
    picurl: str | None = None
    desc: str | None = None


class MiniProgramAttachment(WeComApiModelBase):
    title: str
    pic_media_id: str | None = None
    appid: str
    page: str | None = None


class VideoAttachment(WeComApiModelBase):
    media_id: str


class FileAttachment(WeComApiModelBase):
    media_id: str


class Attachment(WeComApiModelBase):
    """附件模型,根据 msgtype 动态选择不同的附件内容"""

    msgtype: Literal["image", "link", "miniprogram", "video", "file"]
    image: ImageAttachment | None = None
    link: LinkAttachment | None = None
    miniprogram: MiniProgramAttachment | None = None
    video: VideoAttachment | None = None
    file: FileAttachment | None = None


class GetGroupMsgListRequest(WeComApiModelBase):
    chat_type: Literal["single", "group"]
    start_time: Annotated[datetime.datetime | int, AfterValidator(dt_to_int_ts)]
    end_time: Annotated[datetime.datetime | int, AfterValidator(dt_to_int_ts)]
    creator: str | None = None
    filter_type: Literal[0, 1, 2] | None = None
    limit: int | None = 100
    cursor: str | None = None


class GroupMsgItem(WeComApiModelBase):
    msgid: str
    creator: str | None = None
    create_time: int
    create_type: int
    text: TextMessage | None = None
    attachments: list[Attachment] | None = None


class GetGroupMsgListResponse(WeComBaseResp):
    next_cursor: str | None = None
    group_msg_list: list[GroupMsgItem] = Field(default_factory=list)
