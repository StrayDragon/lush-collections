"""
企业微信群发消息模板模型测试

测试 AddMsgTemplateRequest 及相关模型的校验功能
"""

import pytest

from lush_wecom.models.add_msg_template_vo import (
    MAX_ATTACHMENTS_COUNT,
    MAX_CHAT_ID_LIST_COUNT,
    MAX_EXTERNAL_USERID_COUNT,
    MAX_LINK_DESC_BYTES,
    MAX_LINK_PICURL_BYTES,
    MAX_LINK_TITLE_BYTES,
    MAX_LINK_URL_BYTES,
    MAX_MINIPROGRAM_TITLE_BYTES,
    MAX_TAG_LIST_COUNT,
    MAX_TEXT_BYTES,
    AddMsgTemplateRequest,
    AddMsgTemplateResponse,
    Attachment,
    FileAttachment,
    ImageAttachment,
    LinkAttachment,
    MiniProgramAttachment,
    TagFilter,
    TagGroup,
    TextMessage,
    VideoAttachment,
)

# region TextMessage 测试


def test_text_message_valid():
    """测试合法的文本消息"""
    text = TextMessage(content="测试消息")
    assert text.content == "测试消息"


def test_text_message_empty():
    """测试空文本消息"""
    with pytest.raises(ValueError, match="文本内容不能为空"):
        TextMessage(content="")


def test_text_message_too_long():
    """测试文本内容超长"""
    long_content = "测" * 2000  # 每个中文3字节,超过4000字节
    with pytest.raises(ValueError, match="文本内容不能超过.*字节"):
        TextMessage(content=long_content)


def test_text_message_max_length():
    """测试文本最大长度边界"""
    # 4000字节 = 1333个中文字符 + 1个英文字符
    max_content = "测" * 1333 + "a"
    text = TextMessage(content=max_content)
    assert len(text.content.encode("utf-8")) == 4000


# endregion

# region ImageAttachment 测试


def test_image_attachment_with_media_id():
    """测试使用media_id的图片附件"""
    image = ImageAttachment(media_id="MEDIA_ID_123")
    assert image.media_id == "MEDIA_ID_123"


def test_image_attachment_with_pic_url():
    """测试使用pic_url的图片附件"""
    image = ImageAttachment(pic_url="https://example.com/image.jpg")
    assert image.pic_url == "https://example.com/image.jpg"


def test_image_attachment_with_both():
    """测试同时提供media_id和pic_url"""
    image = ImageAttachment(media_id="MEDIA_ID", pic_url="https://example.com/image.jpg")
    assert image.media_id == "MEDIA_ID"
    assert image.pic_url == "https://example.com/image.jpg"


def test_image_attachment_empty():
    """测试图片附件缺少必需字段"""
    with pytest.raises(ValueError, match="图片附件必须提供"):
        ImageAttachment()


# endregion

# region LinkAttachment 测试


def test_link_attachment_valid():
    """测试合法的链接附件"""
    link = LinkAttachment(
        title="测试标题",
        url="https://example.com",
        desc="测试描述",
        picurl="https://example.com/pic.jpg",
    )
    assert link.title == "测试标题"
    assert link.url == "https://example.com"


def test_link_attachment_title_too_long():
    """测试链接标题超长"""
    long_title = "标" * 50  # 150字节,超过128
    with pytest.raises(ValueError, match="链接标题不能超过.*字节"):
        LinkAttachment(title=long_title, url="https://example.com")


def test_link_attachment_url_too_long():
    """测试链接URL超长"""
    long_url = "https://example.com/" + "a" * 2048
    with pytest.raises(ValueError, match="链接URL不能超过.*字节"):
        LinkAttachment(title="标题", url=long_url)


def test_link_attachment_desc_too_long():
    """测试链接描述超长"""
    long_desc = "描" * 200  # 600字节,超过512
    with pytest.raises(ValueError, match="链接描述不能超过.*字节"):
        LinkAttachment(title="标题", url="https://example.com", desc=long_desc)


def test_link_attachment_picurl_too_long():
    """测试链接封面URL超长"""
    long_picurl = "https://example.com/" + "a" * 2048
    with pytest.raises(ValueError, match="链接封面URL不能超过.*字节"):
        LinkAttachment(title="标题", url="https://example.com", picurl=long_picurl)


# endregion

# region MiniProgramAttachment 测试


def test_miniprogram_attachment_valid():
    """测试合法的小程序附件"""
    mp = MiniProgramAttachment(
        title="小程序",
        pic_media_id="MEDIA_ID",
        appid="wx123456",
        page="/pages/index",
    )
    assert mp.title == "小程序"
    assert mp.appid == "wx123456"


def test_miniprogram_attachment_title_too_long():
    """测试小程序标题超长"""
    long_title = "标" * 25  # 75字节,超过64
    with pytest.raises(ValueError, match="小程序标题不能超过.*字节"):
        MiniProgramAttachment(
            title=long_title,
            pic_media_id="MEDIA_ID",
            appid="wx123456",
            page="/pages/index",
        )


# endregion

# region Attachment 测试


def test_attachment_image_valid():
    """测试合法的图片附件"""
    attachment = Attachment(
        msgtype="image",
        image=ImageAttachment(media_id="MEDIA_ID"),
    )
    assert attachment.msgtype == "image"
    assert attachment.image is not None


def test_attachment_link_valid():
    """测试合法的链接附件"""
    attachment = Attachment(
        msgtype="link",
        link=LinkAttachment(title="标题", url="https://example.com"),
    )
    assert attachment.msgtype == "link"
    assert attachment.link is not None


def test_attachment_miniprogram_valid():
    """测试合法的小程序附件"""
    attachment = Attachment(
        msgtype="miniprogram",
        miniprogram=MiniProgramAttachment(
            title="小程序",
            pic_media_id="MEDIA_ID",
            appid="wx123456",
            page="/pages/index",
        ),
    )
    assert attachment.msgtype == "miniprogram"


def test_attachment_video_valid():
    """测试合法的视频附件"""
    attachment = Attachment(
        msgtype="video",
        video=VideoAttachment(media_id="MEDIA_ID"),
    )
    assert attachment.msgtype == "video"


def test_attachment_file_valid():
    """测试合法的文件附件"""
    attachment = Attachment(
        msgtype="file",
        file=FileAttachment(media_id="MEDIA_ID"),
    )
    assert attachment.msgtype == "file"


def test_attachment_msgtype_mismatch():
    """测试附件类型与内容不匹配"""
    with pytest.raises(ValueError, match="msgtype 为 'image' 时,必须提供 image 字段"):
        Attachment(msgtype="image")


# endregion

# region TagGroup 和 TagFilter 测试


def test_tag_group_valid():
    """测试合法的标签组"""
    tag_group = TagGroup(tag_list=["tag1", "tag2", "tag3"])
    assert len(tag_group.tag_list) == 3


def test_tag_group_empty():
    """测试空标签列表"""
    with pytest.raises(ValueError, match="标签列表不能为空"):
        TagGroup(tag_list=[])


def test_tag_group_too_many():
    """测试标签数量超限"""
    too_many_tags = [f"tag{i}" for i in range(MAX_TAG_LIST_COUNT + 1)]
    with pytest.raises(ValueError, match=f"每组标签最多{MAX_TAG_LIST_COUNT}个"):
        TagGroup(tag_list=too_many_tags)


def test_tag_filter_valid():
    """测试合法的标签筛选器"""
    tag_filter = TagFilter(
        group_list=[
            TagGroup(tag_list=["tag1", "tag2"]),
            TagGroup(tag_list=["tag3"]),
        ],
    )
    assert len(tag_filter.group_list) == 2


def test_tag_filter_empty():
    """测试空标签组列表"""
    with pytest.raises(ValueError, match="标签组列表不能为空"):
        TagFilter(group_list=[])


# endregion

# region AddMsgTemplateRequest 基础测试


def test_request_single_with_external_userid():
    """测试发送给指定客户"""
    request = AddMsgTemplateRequest(
        chat_type="single",
        external_userid=["user1", "user2"],
        text=TextMessage(content="测试消息"),
    )
    assert request.chat_type == "single"
    assert len(request.external_userid) == 2


def test_request_single_with_tag_filter():
    """测试使用标签筛选客户"""
    request = AddMsgTemplateRequest(
        chat_type="single",
        sender="zhangsan",
        tag_filter=TagFilter(group_list=[TagGroup(tag_list=["tag1"])]),
        text=TextMessage(content="测试消息"),
    )
    assert request.chat_type == "single"
    assert request.tag_filter is not None


def test_request_group_with_sender():
    """测试发送给客户群"""
    request = AddMsgTemplateRequest(
        chat_type="group",
        sender="zhangsan",
        chat_id_list=["group1"],
        text=TextMessage(content="测试消息"),
    )
    assert request.chat_type == "group"
    assert request.sender == "zhangsan"


def test_request_with_attachments():
    """测试带附件的请求"""
    request = AddMsgTemplateRequest(
        chat_type="single",
        external_userid=["user1"],
        text=TextMessage(content="测试"),
        attachments=[
            Attachment(msgtype="image", image=ImageAttachment(media_id="MEDIA_ID")),
            Attachment(msgtype="link", link=LinkAttachment(title="标题", url="https://example.com")),
        ],
    )
    assert len(request.attachments) == 2


# endregion

# region AddMsgTemplateRequest 校验规则测试


def test_request_empty_content():
    """测试text和attachments同时为空"""
    with pytest.raises(ValueError, match="text 和 attachments 不能同时为空"):
        AddMsgTemplateRequest(
            chat_type="single",
            external_userid=["user1"],
        )


def test_request_single_all_empty():
    """测试single类型时sender、external_userid、tag_filter都为空"""
    with pytest.raises(ValueError, match="sender, external_userid, tag_filter 不可同时为空"):
        AddMsgTemplateRequest(
            chat_type="single",
            text=TextMessage(content="测试"),
        )


def test_request_single_with_external_userid_and_tag_filter():
    """测试single类型同时指定external_userid和tag_filter"""
    with pytest.raises(ValueError, match="tag_filter 不生效"):
        AddMsgTemplateRequest(
            chat_type="single",
            external_userid=["user1"],
            tag_filter=TagFilter(group_list=[TagGroup(tag_list=["tag1"])]),
            text=TextMessage(content="测试"),
        )


def test_request_single_with_chat_id_list():
    """测试single类型使用chat_id_list"""
    with pytest.raises(ValueError, match="chat_type=single 时, chat_id_list 无效"):
        AddMsgTemplateRequest(
            chat_type="single",
            external_userid=["user1"],
            chat_id_list=["group1"],
            text=TextMessage(content="测试"),
        )


def test_request_group_without_sender():
    """测试group类型未提供sender"""
    with pytest.raises(ValueError, match="chat_type=group 时, sender 必填"):
        AddMsgTemplateRequest(
            chat_type="group",
            chat_id_list=["group1"],
            text=TextMessage(content="测试"),
        )


def test_request_group_with_external_userid():
    """测试group类型使用external_userid"""
    with pytest.raises(ValueError, match="chat_type=group 时, external_userid 无效"):
        AddMsgTemplateRequest(
            chat_type="group",
            sender="zhangsan",
            external_userid=["user1"],
            chat_id_list=["group1"],
            text=TextMessage(content="测试"),
        )


# endregion

# region AddMsgTemplateRequest 数量限制测试


def test_request_external_userid_limit():
    """测试客户数量超限"""
    too_many_users = [f"user{i}" for i in range(MAX_EXTERNAL_USERID_COUNT + 1)]
    with pytest.raises(ValueError, match=f"客户列表最多{MAX_EXTERNAL_USERID_COUNT}个"):
        AddMsgTemplateRequest(
            chat_type="single",
            external_userid=too_many_users,
            text=TextMessage(content="测试"),
        )


def test_request_chat_id_list_limit():
    """测试客户群数量超限"""
    too_many_groups = [f"group{i}" for i in range(MAX_CHAT_ID_LIST_COUNT + 1)]
    with pytest.raises(ValueError, match=f"客户群列表最多{MAX_CHAT_ID_LIST_COUNT}个"):
        AddMsgTemplateRequest(
            chat_type="group",
            sender="zhangsan",
            chat_id_list=too_many_groups,
            text=TextMessage(content="测试"),
        )


def test_request_attachments_limit():
    """测试附件数量超限"""
    too_many_attachments = [
        Attachment(msgtype="image", image=ImageAttachment(media_id=f"MEDIA_{i}")) for i in range(MAX_ATTACHMENTS_COUNT + 1)
    ]
    with pytest.raises(ValueError, match=f"附件最多{MAX_ATTACHMENTS_COUNT}个"):
        AddMsgTemplateRequest(
            chat_type="single",
            external_userid=["user1"],
            attachments=too_many_attachments,
        )


def test_request_attachments_max_count():
    """测试附件最大数量边界"""
    max_attachments = [Attachment(msgtype="image", image=ImageAttachment(media_id=f"MEDIA_{i}")) for i in range(MAX_ATTACHMENTS_COUNT)]
    request = AddMsgTemplateRequest(
        chat_type="single",
        external_userid=["user1"],
        attachments=max_attachments,
    )
    assert len(request.attachments) == MAX_ATTACHMENTS_COUNT


# endregion

# region AddMsgTemplateRequest 扩展校验测试


def test_request_extended_external_userid_valid():
    """测试扩展校验: external_userid在允许范围内"""
    request = AddMsgTemplateRequest(
        chat_type="single",
        external_userid=["user1", "user2"],
        text=TextMessage(content="测试"),
        x_allowed_external_userid={"user1", "user2", "user3"},
    )
    assert request.external_userid == ["user1", "user2"]


def test_request_extended_external_userid_invalid():
    """测试扩展校验: external_userid超出允许范围"""
    with pytest.raises(ValueError, match="external_userid 超出允许范围"):
        AddMsgTemplateRequest(
            chat_type="single",
            external_userid=["user1", "user2", "user3"],
            text=TextMessage(content="测试"),
            x_allowed_external_userid={"user1", "user2"},
        )


def test_request_extended_chat_id_list_valid():
    """测试扩展校验: chat_id_list在允许范围内"""
    request = AddMsgTemplateRequest(
        chat_type="group",
        sender="zhangsan",
        chat_id_list=["group1"],
        text=TextMessage(content="测试"),
        x_allowed_chat_id_list={"group1", "group2"},
    )
    assert request.chat_id_list == ["group1"]


def test_request_extended_chat_id_list_invalid():
    """测试扩展校验: chat_id_list超出允许范围"""
    with pytest.raises(ValueError, match="chat_id_list 超出允许范围"):
        AddMsgTemplateRequest(
            chat_type="group",
            sender="zhangsan",
            chat_id_list=["group1", "group2"],
            text=TextMessage(content="测试"),
            x_allowed_chat_id_list={"group1"},
        )


def test_request_extended_tag_filter_valid():
    """测试扩展校验: tag_filter在允许范围内"""
    request = AddMsgTemplateRequest(
        chat_type="single",
        sender="zhangsan",
        tag_filter=TagFilter(group_list=[TagGroup(tag_list=["tag1", "tag2"])]),
        text=TextMessage(content="测试"),
        x_allowed_tag_filter=TagFilter(
            group_list=[
                TagGroup(tag_list=["tag1", "tag2"]),
                TagGroup(tag_list=["tag3"]),
            ],
        ),
    )
    assert request.tag_filter is not None


def test_request_extended_tag_filter_invalid():
    """测试扩展校验: tag_filter超出允许范围"""
    with pytest.raises(ValueError, match="tag_filter 超出允许范围"):
        AddMsgTemplateRequest(
            chat_type="single",
            sender="zhangsan",
            tag_filter=TagFilter(group_list=[TagGroup(tag_list=["tag1", "tag2"])]),
            text=TextMessage(content="测试"),
            x_allowed_tag_filter=TagFilter(group_list=[TagGroup(tag_list=["tag1"])]),
        )


# endregion

# region AddMsgTemplateResponse 测试


def test_response_parse():
    """测试响应模型解析"""
    response = AddMsgTemplateResponse(
        errcode=0,
        errmsg="ok",
        msgid="msg123456",
        fail_list=["user1", "user2"],
    )
    assert response.errcode == 0
    assert response.msgid == "msg123456"
    assert len(response.fail_list) == 2


def test_response_parse_minimal():
    """测试响应模型最小字段"""
    response = AddMsgTemplateResponse(errcode=0, errmsg="ok")
    assert response.errcode == 0
    assert response.msgid is None
    assert response.fail_list is None


# endregion

# region 边界和综合测试


def test_request_all_fields():
    """测试包含所有字段的完整请求"""
    request = AddMsgTemplateRequest(
        chat_type="single",
        external_userid=["user1", "user2"],
        sender="zhangsan",
        allow_select=True,
        text=TextMessage(content="这是测试消息"),
        attachments=[
            Attachment(msgtype="image", image=ImageAttachment(media_id="MEDIA_ID_1")),
            Attachment(
                msgtype="link",
                link=LinkAttachment(
                    title="查看详情",
                    url="https://example.com",
                    desc="点击查看更多",
                    picurl="https://example.com/pic.jpg",
                ),
            ),
            Attachment(
                msgtype="miniprogram",
                miniprogram=MiniProgramAttachment(
                    title="小程序",
                    pic_media_id="MEDIA_ID_2",
                    appid="wx123456",
                    page="/pages/index",
                ),
            ),
            Attachment(msgtype="video", video=VideoAttachment(media_id="MEDIA_ID_3")),
            Attachment(msgtype="file", file=FileAttachment(media_id="MEDIA_ID_4")),
        ],
    )
    assert request.chat_type == "single"
    assert len(request.external_userid) == 2
    assert len(request.attachments) == 5
    assert request.allow_select is True


def test_constants_values():
    """测试常量值是否符合文档"""
    assert MAX_TEXT_BYTES == 4000
    assert MAX_ATTACHMENTS_COUNT == 9
    assert MAX_EXTERNAL_USERID_COUNT == 10000
    assert MAX_CHAT_ID_LIST_COUNT == 2000
    assert MAX_TAG_LIST_COUNT == 100
    assert MAX_LINK_TITLE_BYTES == 128
    assert MAX_LINK_URL_BYTES == 2048
    assert MAX_LINK_DESC_BYTES == 512
    assert MAX_LINK_PICURL_BYTES == 2048
    assert MAX_MINIPROGRAM_TITLE_BYTES == 64


# endregion
