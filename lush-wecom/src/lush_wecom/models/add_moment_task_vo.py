"""
创建客户朋友圈发表任务模型

根据企业微信官方文档: https://developer.work.weixin.qq.com/document/path/95094
"""

from typing import Annotated, Final, Literal

from pydantic import Field, field_validator, model_validator
from typing_extensions import Self

from .common_vo import WeComApiModelBase, WeComBaseResp

# region 企业微信API规范限制

MAX_TEXT_BYTES: Final[int] = 4000
"""文本最大字节数 (对应约2000个汉字)"""

MAX_TEXT_LENGTH: Final[int] = 2000
"""文本最大字符数 (以字符计)"""

MAX_IMAGE_COUNT: Final[int] = 9
"""图片最大数量"""

MAX_VIDEO_COUNT: Final[int] = 1
"""视频最大数量"""

MAX_LINK_COUNT: Final[int] = 1
"""链接最大数量"""

MAX_LINK_TITLE_LENGTH: Final[int] = 64
"""链接标题最大字数"""

MAX_LINK_TITLE_BYTES: Final[int] = 128
"""链接标题最大字节数"""

MAX_LINK_URL_BYTES: Final[int] = 2048
"""链接URL最大字节数 (企微API未明确说明,参考群发消息的限制)"""

# endregion

# region 纯校验函数


def validate_moment_text_content(content: str) -> str:
    """校验朋友圈文本内容长度

    Args:
        content: 文本内容

    Returns:
        校验通过的内容

    Raises:
        ValueError: 内容超过限制
    """
    if not content:
        raise ValueError("文本内容不能为空")

    # 字符数校验
    if len(content) > MAX_TEXT_LENGTH:
        raise ValueError(f"文本内容不能超过{MAX_TEXT_LENGTH}个字符,当前长度: {len(content)}字符")

    # 字节数校验
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > MAX_TEXT_BYTES:
        raise ValueError(f"文本内容不能超过{MAX_TEXT_BYTES}个字节,当前长度: {len(content_bytes)}字节")

    return content


def validate_moment_attachments_count(
    msgtype: Literal["image", "video", "link"],
    count: int,
) -> None:
    """校验朋友圈附件数量

    朋友圈附件规则:
    - 图片: 最多9张
    - 视频: 最多1个
    - 链接: 最多1个
    - 三种类型不可混合使用

    Args:
        msgtype: 附件类型
        count: 附件数量

    Raises:
        ValueError: 数量超过限制
    """
    max_count = {
        "image": MAX_IMAGE_COUNT,
        "video": MAX_VIDEO_COUNT,
        "link": MAX_LINK_COUNT,
    }.get(msgtype, 0)

    if count > max_count:
        type_name = {"image": "图片", "video": "视频", "link": "链接"}.get(msgtype, msgtype)
        raise ValueError(f"{type_name}最多{max_count}个,当前数量: {count}")


def validate_moment_attachments_mixed_type(attachments: list["AddMomentAttachment"]) -> None:
    """校验朋友圈附件是否混合了不同类型

    Args:
        attachments: 附件列表

    Raises:
        ValueError: 附件类型混合
    """
    if not attachments:
        return

    types = {att.msgtype for att in attachments}
    if len(types) > 1:
        raise ValueError("朋友圈附件只能选择一种类型(图片/视频/链接),不能混合使用")


def validate_moment_link_title(title: str) -> str:
    """校验链接标题长度

    根据企微API规范: 图文消息标题最多64个字(128个字节)

    Args:
        title: 链接标题

    Returns:
        校验通过的标题

    Raises:
        ValueError: 标题超过限制
    """
    if not title:
        raise ValueError("链接标题不能为空")

    # 字符数校验
    if len(title) > MAX_LINK_TITLE_LENGTH:
        raise ValueError(f"链接标题不能超过{MAX_LINK_TITLE_LENGTH}个字,当前长度: {len(title)}字")

    # 字节数校验
    title_bytes = title.encode("utf-8")
    if len(title_bytes) > MAX_LINK_TITLE_BYTES:
        raise ValueError(f"链接标题不能超过{MAX_LINK_TITLE_BYTES}个字节,当前长度: {len(title_bytes)}字节")

    return title


def validate_moment_link_url(url: str) -> str:
    """校验链接URL长度

    Args:
        url: 链接URL

    Returns:
        校验通过的URL

    Raises:
        ValueError: URL超过限制
    """
    if not url:
        raise ValueError("链接URL不能为空")
    url_bytes = url.encode("utf-8")
    if len(url_bytes) > MAX_LINK_URL_BYTES:
        raise ValueError(f"链接URL不能超过{MAX_LINK_URL_BYTES}个字节,当前长度: {len(url_bytes)}字节")
    return url


def validate_moment_content(
    text: "AddMomentText | None",
    attachments: list["AddMomentAttachment"] | None,
) -> None:
    """校验朋友圈发送内容

    规则:
    - 文本和附件至少要有一个
    - 附件类型不可混合

    Args:
        text: 文本内容
        attachments: 附件列表

    Raises:
        ValueError: 内容不符合规则
    """
    has_text = text is not None and text.content
    has_attachments = attachments is not None and len(attachments) > 0

    if not has_text and not has_attachments:
        raise ValueError("发送内容不能为空,文本和附件至少要有一个")

    if attachments is not None and len(attachments) > 0:
        validate_moment_attachments_mixed_type(attachments)

        # 检查各类型数量
        msgtype = attachments[0].msgtype
        validate_moment_attachments_count(msgtype, len(attachments))


# endregion


class AddMomentText(WeComApiModelBase):
    """朋友圈文本内容"""

    content: Annotated[str, Field(description=f"文本内容,最多{MAX_TEXT_LENGTH}个字符/{MAX_TEXT_BYTES}个字节")]

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        return validate_moment_text_content(v)


class AddMomentImageAttachment(WeComApiModelBase):
    """朋友圈图片附件"""

    media_id: Annotated[str, Field(description="图片的media_id")]


class AddMomentVideoAttachment(WeComApiModelBase):
    """朋友圈视频附件"""

    media_id: Annotated[str, Field(description="视频的media_id")]


class AddMomentLinkAttachment(WeComApiModelBase):
    """朋友圈链接附件"""

    title: Annotated[str, Field(description=f"链接标题,最多{MAX_LINK_TITLE_LENGTH}个字({MAX_LINK_TITLE_BYTES}个字节)")]
    url: Annotated[str, Field(description="链接URL")]
    media_id: Annotated[str, Field(description="链接封面图的media_id,可通过上传附件资源接口获得")]

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        return validate_moment_link_title(v)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        return validate_moment_link_url(v)


class AddMomentAttachment(WeComApiModelBase):
    """朋友圈附件"""

    msgtype: Annotated[Literal["image", "video", "link"], Field(description="附件类型")]
    image: AddMomentImageAttachment | None = None
    video: AddMomentVideoAttachment | None = None
    link: AddMomentLinkAttachment | None = None

    @model_validator(mode="after")
    def validate_attachment(self) -> Self:
        """校验附件内容与msgtype匹配"""
        msgtype_field_map = {
            "image": (self.image, "image"),
            "video": (self.video, "video"),
            "link": (self.link, "link"),
        }
        field_value, field_name = msgtype_field_map[self.msgtype]
        if field_value is None:
            raise ValueError(f"msgtype 为 '{self.msgtype}' 时,必须提供 {field_name} 字段")
        return self


class AddMomentSenderList(WeComApiModelBase):
    user_list: list[str] | None = None
    department_list: list[int] | None = None


class AddMomentExternalContactList(WeComApiModelBase):
    tag_list: list[str] | None = None


class AddMomentVisibleRange(WeComApiModelBase):
    sender_list: AddMomentSenderList | None = None
    external_contact_list: AddMomentExternalContactList | None = None


class AddMomentTaskRequest(WeComApiModelBase):
    """创建朋友圈发表任务请求"""

    text: Annotated[AddMomentText | None, Field(description="文本内容")] = None
    attachments: Annotated[
        list[AddMomentAttachment] | None,
        Field(description=f"附件列表,图片最多{MAX_IMAGE_COUNT}张,视频最多{MAX_VIDEO_COUNT}个,链接最多{MAX_LINK_COUNT}个"),
    ] = None
    visible_range: Annotated[AddMomentVisibleRange | None, Field(description="可见范围")] = None

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        """校验整体请求"""
        validate_moment_content(self.text, self.attachments)
        return self


class AddMomentTaskResponse(WeComBaseResp):
    jobid: Annotated[str | None, Field(description="异步任务ID,24小时有效")] = None
