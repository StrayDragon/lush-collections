"""
企业微信群发消息模板相关模型

根据企业微信官方文档: https://developer.work.weixin.qq.com/document/path/92135
"""

from typing import Annotated, Final, Literal

from pydantic import Field, field_validator, model_validator
from typing_extensions import Self

from .common_vo import WeComApiModelBase, WeComBaseResp

# region 企业微信API规范限制
MAX_TEXT_BYTES: Final[int] = 4000
"""文本最大字节数"""

MAX_ATTACHMENTS_COUNT: Final[int] = 9
"""附件最大数量"""

MAX_EXTERNAL_USERID_COUNT: Final[int] = 10000
"""客户最大数量(chat_type=single时)"""

MAX_CHAT_ID_LIST_COUNT: Final[int] = 2000
"""客户群最大数量(chat_type=group时)"""

MAX_TAG_LIST_COUNT: Final[int] = 100
"""每组标签最大数量"""

MAX_LINK_TITLE_BYTES: Final[int] = 128
"""链接标题最大字节数"""

MAX_LINK_URL_BYTES: Final[int] = 2048
"""链接URL最大字节数"""

MAX_LINK_DESC_BYTES: Final[int] = 512
"""链接描述最大字节数"""

MAX_LINK_PICURL_BYTES: Final[int] = 2048
"""链接封面URL最大字节数"""

MAX_MINIPROGRAM_TITLE_BYTES: Final[int] = 64
"""小程序标题最大字节数"""
# endregion

# region 纯校验函数


def validate_text_content(content: str) -> str:
    """校验文本内容长度"""
    if not content:
        raise ValueError("文本内容不能为空")
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > MAX_TEXT_BYTES:
        raise ValueError(f"文本内容不能超过{MAX_TEXT_BYTES}个字节,当前长度: {len(content_bytes)}字节")
    return content


def validate_image_attachment(media_id: str | None = None, pic_url: str | None = None) -> None:
    """校验图片附件: media_id 和 pic_url 至少提供一个"""
    if not media_id and not pic_url:
        raise ValueError("图片附件必须提供 media_id 或 pic_url 中的至少一个")


def validate_link_title(title: str) -> str:
    """校验链接标题长度"""
    if not title:
        raise ValueError("链接标题不能为空")
    title_bytes = title.encode("utf-8")
    if len(title_bytes) > MAX_LINK_TITLE_BYTES:
        raise ValueError(f"链接标题不能超过{MAX_LINK_TITLE_BYTES}个字节,当前长度: {len(title_bytes)}字节")
    return title


def validate_link_url(url: str) -> str:
    """校验链接URL长度"""
    if not url:
        raise ValueError("链接URL不能为空")
    url_bytes = url.encode("utf-8")
    if len(url_bytes) > MAX_LINK_URL_BYTES:
        raise ValueError(f"链接URL不能超过{MAX_LINK_URL_BYTES}个字节,当前长度: {len(url_bytes)}字节")
    return url


def validate_link_desc(desc: str | None) -> str | None:
    """校验链接描述长度"""
    if desc:
        desc_bytes = desc.encode("utf-8")
        if len(desc_bytes) > MAX_LINK_DESC_BYTES:
            raise ValueError(f"链接描述不能超过{MAX_LINK_DESC_BYTES}个字节,当前长度: {len(desc_bytes)}字节")
    return desc


def validate_link_picurl(picurl: str | None) -> str | None:
    """校验链接封面URL长度"""
    if picurl:
        picurl_bytes = picurl.encode("utf-8")
        if len(picurl_bytes) > MAX_LINK_PICURL_BYTES:
            raise ValueError(f"链接封面URL不能超过{MAX_LINK_PICURL_BYTES}个字节,当前长度: {len(picurl_bytes)}字节")
    return picurl


def validate_miniprogram_title(title: str) -> str:
    """校验小程序标题长度"""
    if not title:
        raise ValueError("小程序标题不能为空")
    title_bytes = title.encode("utf-8")
    if len(title_bytes) > MAX_MINIPROGRAM_TITLE_BYTES:
        raise ValueError(f"小程序标题不能超过{MAX_MINIPROGRAM_TITLE_BYTES}个字节,当前长度: {len(title_bytes)}字节")
    return title


def validate_attachment_msgtype(
    msgtype: str,
    image: "ImageAttachment | None",
    link: "LinkAttachment | None",
    miniprogram: "MiniProgramAttachment | None",
    video: "VideoAttachment | None",
    file: "FileAttachment | None",
) -> None:
    """校验附件内容与 msgtype 匹配"""
    msgtype_field_map = {
        "image": (image, "image"),
        "link": (link, "link"),
        "miniprogram": (miniprogram, "miniprogram"),
        "video": (video, "video"),
        "file": (file, "file"),
    }

    field_value, field_name = msgtype_field_map[msgtype]
    if field_value is None:
        raise ValueError(f"msgtype 为 '{msgtype}' 时,必须提供 {field_name} 字段")


def validate_tag_list(tag_list: list[str]) -> list[str]:
    """校验标签列表"""
    if not tag_list:
        raise ValueError("标签列表不能为空")
    if len(tag_list) > MAX_TAG_LIST_COUNT:
        raise ValueError(f"每组标签最多{MAX_TAG_LIST_COUNT}个,当前数量: {len(tag_list)}")
    return tag_list


def validate_tag_group_list(group_list: list["TagGroup"]) -> list["TagGroup"]:
    """校验标签组列表"""
    if not group_list:
        raise ValueError("标签组列表不能为空")
    return group_list


def validate_external_userid_count(external_userid: list[str] | None) -> list[str] | None:
    """校验客户列表数量"""
    if external_userid and len(external_userid) > MAX_EXTERNAL_USERID_COUNT:
        raise ValueError(f"客户列表最多{MAX_EXTERNAL_USERID_COUNT}个,当前数量: {len(external_userid)}")
    return external_userid


def validate_chat_id_list_count(chat_id_list: list[str] | None) -> list[str] | None:
    """校验客户群列表数量"""
    if chat_id_list and len(chat_id_list) > MAX_CHAT_ID_LIST_COUNT:
        raise ValueError(f"客户群列表最多{MAX_CHAT_ID_LIST_COUNT}个,当前数量: {len(chat_id_list)}")
    return chat_id_list


def validate_attachments_count(attachments: list["Attachment"] | None) -> list["Attachment"] | None:
    """校验附件数量"""
    if attachments and len(attachments) > MAX_ATTACHMENTS_COUNT:
        raise ValueError(f"附件最多{MAX_ATTACHMENTS_COUNT}个,当前数量: {len(attachments)}")
    return attachments


def validate_add_msg_template_request(
    chat_type: str,
    text: "TextMessage | None",
    attachments: list["Attachment"] | None,
    sender: str | None,
    external_userid: list[str] | None,
    tag_filter: "TagFilter | None",
    chat_id_list: list[str] | None,
) -> None:
    """校验群发请求整体规则"""
    # 1. text 和 attachments 不能同时为空
    if not text and not attachments:
        raise ValueError("text 和 attachments 不能同时为空")

    # 2. chat_type=single 时的校验
    if chat_type == "single":
        # external_userid, tag_filter 不可同时为空
        if not sender and not external_userid and not tag_filter:
            raise ValueError("chat_type=single 时, sender, external_userid, tag_filter 不可同时为空")

        # 如果指定了 external_userid, 则 tag_filter 不生效
        if external_userid and tag_filter:
            raise ValueError("指定了 external_userid 时, tag_filter 不生效,请只使用其中一个")

        # chat_id_list 仅在 group 时有效
        if chat_id_list:
            raise ValueError("chat_type=single 时, chat_id_list 无效")

    # 3. chat_type=group 时的校验
    if chat_type == "group":
        # sender 必填
        if not sender:
            raise ValueError("chat_type=group 时, sender 必填")

        # external_userid 仅在 single 时有效
        if external_userid:
            raise ValueError("chat_type=group 时, external_userid 无效")


# endregion


class TextMessage(WeComApiModelBase):
    """文本消息"""

    content: Annotated[str, Field(description=f"文本内容,最多{MAX_TEXT_BYTES}个字节")]

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        return validate_text_content(v)


class ImageAttachment(WeComApiModelBase):
    """图片附件"""

    media_id: Annotated[str | None, Field(description="图片的media_id")] = None
    pic_url: Annotated[str | None, Field(description="图片的链接")] = None

    @model_validator(mode="after")
    def validate_image(self) -> Self:
        validate_image_attachment(self.media_id, self.pic_url)
        return self


class LinkAttachment(WeComApiModelBase):
    """链接附件"""

    title: Annotated[str, Field(description=f"图文消息标题,最长{MAX_LINK_TITLE_BYTES}个字节")]
    url: Annotated[str, Field(description=f"图文消息的链接,最长{MAX_LINK_URL_BYTES}个字节")]
    picurl: Annotated[str | None, Field(description=f"图文消息封面的url,最长{MAX_LINK_PICURL_BYTES}个字节")] = None
    desc: Annotated[str | None, Field(description=f"图文消息的描述,最多{MAX_LINK_DESC_BYTES}个字节")] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        return validate_link_title(v)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        return validate_link_url(v)

    @field_validator("desc")
    @classmethod
    def validate_desc(cls, v: str | None) -> str | None:
        return validate_link_desc(v)

    @field_validator("picurl")
    @classmethod
    def validate_picurl(cls, v: str | None) -> str | None:
        return validate_link_picurl(v)


class MiniProgramAttachment(WeComApiModelBase):
    """小程序附件"""

    title: Annotated[str, Field(description=f"小程序消息标题,最多{MAX_MINIPROGRAM_TITLE_BYTES}个字节")]
    pic_media_id: Annotated[str, Field(description="小程序消息封面的mediaid")]
    appid: Annotated[str, Field(description="小程序appid,必须是关联到企业的小程序应用")]
    page: Annotated[str, Field(description="小程序page路径")]

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        return validate_miniprogram_title(v)


class VideoAttachment(WeComApiModelBase):
    """视频附件"""

    media_id: Annotated[str, Field(description="视频的media_id")]


class FileAttachment(WeComApiModelBase):
    """文件附件"""

    media_id: Annotated[str, Field(description="文件的media_id")]


class Attachment(WeComApiModelBase):
    """附件模型,根据 msgtype 动态选择不同的附件内容"""

    msgtype: Literal["image", "link", "miniprogram", "video", "file"] = Field(..., description="附件类型")
    image: Annotated[ImageAttachment | None, Field(description="图片附件")] = None
    link: Annotated[LinkAttachment | None, Field(description="链接附件")] = None
    miniprogram: Annotated[MiniProgramAttachment | None, Field(description="小程序附件")] = None
    video: Annotated[VideoAttachment | None, Field(description="视频附件")] = None
    file: Annotated[FileAttachment | None, Field(description="文件附件")] = None

    @model_validator(mode="after")
    def validate_attachment(self) -> Self:
        validate_attachment_msgtype(self.msgtype, self.image, self.link, self.miniprogram, self.video, self.file)
        return self


class TagGroup(WeComApiModelBase):
    """标签组"""

    tag_list: Annotated[list[str], Field(description="标签列表")]

    @field_validator("tag_list")
    @classmethod
    def validate_tag_list_field(cls, v: list[str]) -> list[str]:
        return validate_tag_list(v)


class TagFilter(WeComApiModelBase):
    """标签筛选器"""

    group_list: Annotated[list[TagGroup], Field(description="标签组列表,不同组按且关系筛选,同组标签按或关系筛选")]

    @field_validator("group_list")
    @classmethod
    def validate_group_list_field(cls, v: list[TagGroup]) -> list[TagGroup]:
        return validate_tag_group_list(v)


class AddMsgTemplateRequest(WeComApiModelBase):
    """
    创建企业群发请求模型

    根据企业微信官方文档规范实现完整校验
    """

    chat_type: Annotated[Literal["single", "group"], Field(description="群发任务类型: single=发送给客户, group=发送给客户群")] = "single"
    external_userid: Annotated[
        list[str] | None, Field(description=f"客户的external_userid列表,仅chat_type=single时有效,最多{MAX_EXTERNAL_USERID_COUNT}个")
    ] = None
    chat_id_list: Annotated[list[str] | None, Field(description=f"客户群id列表,仅chat_type=group时有效,最多{MAX_CHAT_ID_LIST_COUNT}个")] = (
        None
    )
    tag_filter: Annotated[TagFilter | None, Field(description="客户标签筛选器,不同组按且关系筛选,同组标签按或关系筛选")] = None
    sender: Annotated[str | None, Field(description="发送企业群发消息的成员userid,chat_type=group时必填")] = None
    allow_select: Annotated[bool, Field(default=False, description="是否允许成员重新选择客户列表,仅客户群发场景支持")] = False
    text: Annotated[TextMessage | None, Field(description="文本消息")] = None
    attachments: Annotated[list[Attachment] | None, Field(description=f"附件列表,最多{MAX_ATTACHMENTS_COUNT}个")] = None

    # 扩展校验字段
    x_allowed_external_userid: Annotated[
        set[str] | None,
        Field(
            exclude=True,
            description="扩展校验: 限制允许的external_userid范围, 白名单模式",
        ),
    ] = None
    x_allowed_chat_id_list: Annotated[
        set[str] | None,
        Field(
            exclude=True,
            description="扩展校验: 限制允许的chat_id_list范围, 白名单模式",
        ),
    ] = None
    x_allowed_tag_filter: Annotated[
        TagFilter | None,
        Field(
            exclude=True,
            description="扩展校验: 限制允许的tag_filter范围, 白名单模式",
        ),
    ] = None

    @field_validator("external_userid")
    @classmethod
    def validate_external_userid_field(cls, v: list[str] | None) -> list[str] | None:
        return validate_external_userid_count(v)

    @field_validator("chat_id_list")
    @classmethod
    def validate_chat_id_list_field(cls, v: list[str] | None) -> list[str] | None:
        return validate_chat_id_list_count(v)

    @field_validator("attachments")
    @classmethod
    def validate_attachments_field(cls, v: list[Attachment] | None) -> list[Attachment] | None:
        return validate_attachments_count(v)

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        validate_add_msg_template_request(
            self.chat_type,
            self.text,
            self.attachments,
            self.sender,
            self.external_userid,
            self.tag_filter,
            self.chat_id_list,
        )
        return self

    @model_validator(mode="after")
    def validate_extended_filters(self) -> Self:
        """校验扩展限制字段"""
        # 校验 external_userid 范围
        if self.x_allowed_external_userid and self.external_userid:
            if not set(self.external_userid).issubset(self.x_allowed_external_userid):
                raise ValueError("external_userid 超出允许范围")

        # 校验 chat_id_list 范围
        if self.x_allowed_chat_id_list and self.chat_id_list:
            if not set(self.chat_id_list).issubset(self.x_allowed_chat_id_list):
                raise ValueError("chat_id_list 超出允许范围")

        # 校验 tag_filter 范围
        if self.x_allowed_tag_filter and self.tag_filter:
            current_groups = {frozenset(group.tag_list) for group in self.tag_filter.group_list}
            allowed_groups = {frozenset(group.tag_list) for group in self.x_allowed_tag_filter.group_list}
            if not current_groups.issubset(allowed_groups):
                raise ValueError("tag_filter 超出允许范围")

        return self


class AddMsgTemplateResponse(WeComBaseResp):
    """创建企业群发响应模型"""

    fail_list: Annotated[list[str] | None, Field(description="无效或无法发送的external_userid或chatid列表")] = None
    msgid: Annotated[str | None, Field(description="企业群发消息的id")] = None
