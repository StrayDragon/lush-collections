"""
发送应用消息相关模型
参考文档: https://developer.work.weixin.qq.com/document/path/90236
"""

from typing import Annotated, Literal

from pydantic import Field

from .common_vo import WeComApiModelBase, WeComBaseResp

# ===== 消息内容模型 =====


class TextContent(WeComApiModelBase):
    """文本消息内容"""

    content: str = Field(..., description="消息内容,最长不超过2048个字节,超过将截断")


class ImageContent(WeComApiModelBase):
    """图片消息内容"""

    media_id: str = Field(..., description="图片媒体文件id,可以调用上传临时素材接口获取")


class VoiceContent(WeComApiModelBase):
    """语音消息内容"""

    media_id: str = Field(..., description="语音文件id,可以调用上传临时素材接口获取")


class VideoContent(WeComApiModelBase):
    """视频消息内容"""

    media_id: str = Field(..., description="视频媒体文件id,可以调用上传临时素材接口获取")
    title: str | None = Field(None, description="视频消息的标题,不超过128个字节,超过会自动截断")
    description: str | None = Field(None, description="视频消息的描述,不超过512个字节,超过会自动截断")


class FileContent(WeComApiModelBase):
    """文件消息内容"""

    media_id: str = Field(..., description="文件id,可以调用上传临时素材接口获取")


class TextCardContent(WeComApiModelBase):
    """文本卡片消息内容"""

    title: str = Field(..., description="标题,不超过128个字符,超过会自动截断")
    description: str = Field(..., description="描述,不超过512个字符,超过会自动截断")
    url: str = Field(..., description="点击后跳转的链接最长2048字节,请确保包含了协议头(http/https)")
    btntxt: str | None = Field(None, description='按钮文字默认为"详情",不超过4个文字,超过自动截断')


class NewsArticle(WeComApiModelBase):
    """图文消息文章"""

    title: str = Field(..., description="标题,不超过128个字节,超过会自动截断")
    description: str | None = Field(None, description="描述,不超过512个字节,超过会自动截断")
    url: str | None = Field(None, description="点击后跳转的链接最长2048字节,请确保包含了协议头(http/https),小程序或者url必须填写一个")
    picurl: str | None = Field(None, description="图文消息的图片链接,最长2048字节,支持JPG、PNG格式,较好的效果为大图 1068*455,小图150*150")
    appid: str | None = Field(None, description="小程序appid,必须是与当前应用关联的小程序,appid和pagepath必须同时填写,填写后会忽略url字段")
    pagepath: str | None = Field(
        None, description="点击消息卡片后的小程序页面,最长128字节,仅限本小程序内的页面appid和pagepath必须同时填写,填写后会忽略url字段"
    )


class NewsContent(WeComApiModelBase):
    """图文消息内容"""

    articles: list[NewsArticle] = Field(..., description="图文消息,一个图文消息支持1到8条图文")


class MpNewsArticle(WeComApiModelBase):
    """图文消息(mpnews)文章"""

    title: str = Field(..., description="标题,不超过128个字节,超过会自动截断")
    thumb_media_id: str = Field(
        ..., description="图文消息缩略图的media_id, 可以通过素材管理接口获得此处thumb_media_id即上传接口返回的media_id"
    )
    author: str | None = Field(None, description="图文消息的作者,不超过64个字节")
    content_source_url: str | None = Field(None, description='图文消息点击"阅读原文"之后的页面链接')
    content: str = Field(..., description="图文消息的内容,支持html标签,不超过666 K个字节")
    digest: str | None = Field(None, description="图文消息的描述,不超过512个字节,超过会自动截断")


class MpNewsContent(WeComApiModelBase):
    """图文消息(mpnews)内容"""

    articles: list[MpNewsArticle] = Field(..., description="图文消息,一个图文消息支持1到8条图文")


class MarkdownContent(WeComApiModelBase):
    """markdown消息内容"""

    content: str = Field(..., description="markdown内容,最长不超过2048个字节,必须是utf8编码")


class ContentItem(WeComApiModelBase):
    """小程序通知消息内容项"""

    key: str | None = Field(None, description="长度10个汉字以内")
    value: str | None = Field(None, description="长度30个汉字以内key和value两个字段同时为空时,该键值对将被忽略")


class MiniProgramNoticeContent(WeComApiModelBase):
    """小程序通知消息内容"""

    appid: str = Field(..., description="小程序appid,必须是与当前应用关联的小程序")
    page: str | None = Field(None, description="点击消息卡片后的小程序页面,最长1024个字节,仅限本小程序内的页面该字段不填则消息点击后不跳转")
    title: str = Field(..., description="消息标题,长度限制4-12个汉字")
    description: str | None = Field(None, description="消息描述,长度限制4-12个汉字")
    emphasis_first_item: bool | None = Field(None, description="是否放大第一个content_item")
    content_item: list[ContentItem] | None = Field(None, description="消息内容键值对,最多允许10个item")


# ===== 模板卡片消息相关模型 =====


class TemplateCardSource(WeComApiModelBase):
    """卡片来源样式信息"""

    icon_url: str | None = Field(None, description="来源图片的url,来源图片的尺寸建议为72*72")
    desc: str | None = Field(None, description="来源图片的描述,建议不超过20个字")
    desc_color: Literal[0, 1, 2, 3] | None = Field(None, description="来源文字的颜色,目前支持:0(默认) 灰色,1 黑色,2 红色,3 绿色")


class ActionMenuItem(WeComApiModelBase):
    """操作菜单项"""

    text: str = Field(..., description="操作的描述文案")
    key: str = Field(
        ..., description="操作key值,用户点击后,会产生回调事件将本参数作为EventKey返回,回调事件会带上该key值,最长支持1024字节,不可重复"
    )


class ActionMenu(WeComApiModelBase):
    """卡片右上角更多操作按钮"""

    desc: str | None = Field(None, description="更多操作界面的描述")
    action_list: list[ActionMenuItem] = Field(..., description="操作列表,列表长度取值范围为 [1, 3]")


class MainTitle(WeComApiModelBase):
    """主标题"""

    title: str | None = Field(None, description="一级标题,建议不超过36个字")
    desc: str | None = Field(None, description="标题辅助信息,建议不超过44个字")


class QuoteArea(WeComApiModelBase):
    """引用文献样式"""

    type: Literal[0, 1, 2] | None = Field(
        None, description="引用文献样式区域点击事件,0或不填代表没有点击事件,1 代表跳转url,2 代表跳转小程序"
    )
    url: str | None = Field(None, description="点击跳转的url,quote_area.type是1时必填")
    appid: str | None = Field(None, description="点击跳转的小程序的appid,必须是与当前应用关联的小程序,quote_area.type是2时必填")
    pagepath: str | None = Field(None, description="点击跳转的小程序的pagepath,quote_area.type是2时选填")
    title: str | None = Field(None, description="引用文献样式的标题")
    quote_text: str | None = Field(None, description="引用文献样式的引用文案")


class EmphasisContent(WeComApiModelBase):
    """关键数据样式"""

    title: str | None = Field(None, description="关键数据样式的数据内容,建议不超过14个字")
    desc: str | None = Field(None, description="关键数据样式的数据描述内容,建议不超过22个字")


class HorizontalContentItem(WeComApiModelBase):
    """二级标题+文本列表项"""

    type: Literal[0, 1, 2, 3] | None = Field(
        None, description="链接类型,0或不填代表不是链接,1 代表跳转url,2 代表下载附件,3 代表点击跳转成员详情"
    )
    keyname: str = Field(..., description="二级标题,建议不超过5个字")
    value: str | None = Field(
        None, description="二级文本,如果horizontal_content_list.type是2,该字段代表文件名称(要包含文件类型),建议不超过30个字"
    )
    url: str | None = Field(None, description="链接跳转的url,horizontal_content_list.type是1时必填")
    media_id: str | None = Field(None, description="附件的media_id,horizontal_content_list.type是2时必填")
    userid: str | None = Field(None, description="成员详情的userid,horizontal_content_list.type是3时必填")


class JumpListItem(WeComApiModelBase):
    """跳转指引样式列表项"""

    type: Literal[0, 1, 2] | None = Field(None, description="跳转链接类型,0或不填代表不是链接,1 代表跳转url,2 代表跳转小程序")
    title: str = Field(..., description="跳转链接样式的文案内容,建议不超过18个字")
    url: str | None = Field(None, description="跳转链接的url,jump_list.type是1时必填")
    appid: str | None = Field(None, description="跳转链接的小程序的appid,必须是与当前应用关联的小程序,jump_list.type是2时必填")
    pagepath: str | None = Field(None, description="跳转链接的小程序的pagepath,jump_list.type是2时选填")


class CardAction(WeComApiModelBase):
    """整体卡片的点击跳转事件"""

    type: Literal[0, 1, 2] = Field(..., description="跳转事件类型,0或不填代表不是链接,1 代表跳转url,2 代表打开小程序")
    url: str | None = Field(None, description="跳转事件的url,card_action.type是1时必填")
    appid: str | None = Field(None, description="跳转事件的小程序的appid,必须是与当前应用关联的小程序,card_action.type是2时必填")
    pagepath: str | None = Field(None, description="跳转事件的小程序的pagepath,card_action.type是2时选填")


class ImageTextArea(WeComApiModelBase):
    """左图右文样式"""

    type: Literal[0, 1, 2] | None = Field(
        None, description="左图右文样式区域点击事件,0或不填代表没有点击事件,1 代表跳转url,2 代表跳转小程序"
    )
    url: str | None = Field(None, description="点击跳转的url,image_text_area.type是1时必填")
    appid: str | None = Field(None, description="点击跳转的小程序的appid,必须是与当前应用关联的小程序,image_text_area.type是2时必填")
    pagepath: str | None = Field(None, description="点击跳转的小程序的pagepath,image_text_area.type是2时选填")
    title: str | None = Field(None, description="左图右文样式的标题")
    desc: str | None = Field(None, description="左图右文样式的描述")
    image_url: str = Field(..., description="左图右文样式的图片url")


class CardImage(WeComApiModelBase):
    """图片样式"""

    url: str = Field(..., description="图片的url")
    aspect_ratio: float | None = Field(None, description="图片的宽高比,宽高比要小于2.25,大于1.3,不填该参数默认1.3")


class VerticalContentItem(WeComApiModelBase):
    """卡片二级垂直内容项"""

    title: str = Field(..., description="卡片二级标题,建议不超过38个字")
    desc: str | None = Field(None, description="二级普通文本,建议不超过160个字")


class ButtonSelectionOption(WeComApiModelBase):
    """按钮型卡片的下拉框选项"""

    id: str = Field(
        ..., description="下拉式的选择器选项的id,用户提交后,会产生回调事件,回调事件会带上该id值表示该选项,最长支持128字节,不可重复"
    )
    text: str = Field(..., description="下拉式的选择器选项的文案,建议不超过16个字")


class ButtonSelection(WeComApiModelBase):
    """按钮型卡片的下拉框样式"""

    question_key: str = Field(
        ..., description="下拉式的选择器的key,用户提交选项后,会产生回调事件,回调事件会带上该key值表示该题,最长支持1024字节"
    )
    title: str | None = Field(None, description="下拉式的选择器左边的标题")
    option_list: list[ButtonSelectionOption] = Field(..., description="选项列表,下拉选项不超过 10 个,最少1个")
    selected_id: str | None = Field(None, description="默认选定的id,不填或错填默认第一个")


class ButtonItem(WeComApiModelBase):
    """按钮列表项"""

    type: Literal[0, 1] | None = Field(None, description="按钮点击事件类型,0 或不填代表回调点击事件,1 代表跳转url")
    text: str = Field(..., description="按钮文案,建议不超过10个字")
    style: Literal[1, 2, 3, 4] | None = Field(None, description="按钮样式,目前可填1~4,不填或错填默认1")
    key: str | None = Field(
        None,
        description="按钮key值,用户点击后,会产生回调事件将本参数作为EventKey返回,回调事件会带上该key值,最长支持1024字节,不可重复,button_list.type是0时必填",
    )
    url: str | None = Field(None, description="跳转事件的url,button_list.type是1时必填")


class CheckboxOption(WeComApiModelBase):
    """选择题选项"""

    id: str = Field(..., description="选项id,用户提交选项后,会产生回调事件,回调事件会带上该id值表示该选项,最长支持128字节,不可重复")
    text: str = Field(..., description="选项文案描述,建议不超过17个字")
    is_checked: bool = Field(..., description="该选项是否要默认选中")


class Checkbox(WeComApiModelBase):
    """选择题样式"""

    question_key: str = Field(..., description="选择题key值,用户提交选项后,会产生回调事件,回调事件会带上该key值表示该题,最长支持1024字节")
    mode: Literal[0, 1] | None = Field(None, description="选择题模式,单选:0,多选:1,不填默认0")
    option_list: list[CheckboxOption] = Field(..., description="选项list,选项个数不超过 20 个,最少1个")


class SubmitButton(WeComApiModelBase):
    """提交按钮样式"""

    text: str = Field(..., description="按钮文案,建议不超过10个字,不填默认为提交")
    key: str = Field(..., description="提交按钮的key,会产生回调事件将本参数作为EventKey返回,最长支持1024字节")


class SelectOption(WeComApiModelBase):
    """多项选择型卡片的选项"""

    id: str = Field(
        ..., description="下拉式的选择器选项的id,用户提交选项后,会产生回调事件,回调事件会带上该id值表示该选项,最长支持128字节,不可重复"
    )
    text: str = Field(..., description="下拉式的选择器选项的文案,建议不超过16个字")


class SelectList(WeComApiModelBase):
    """下拉式的选择器列表"""

    question_key: str = Field(
        ..., description="下拉式的选择器题目的key,用户提交选项后,会产生回调事件,回调事件会带上该key值表示该题,最长支持1024字节,不可重复"
    )
    title: str | None = Field(None, description="下拉式的选择器上面的title")
    option_list: list[SelectOption] = Field(..., description="选项列表,下拉选项不超过 10 个,最少1个")
    selected_id: str | None = Field(None, description="默认选定的id,不填或错填默认第一个")


class TemplateCardContent(WeComApiModelBase):
    """模板卡片消息内容"""

    card_type: Literal["text_notice", "news_notice", "button_interaction", "vote_interaction", "multiple_interaction"] = Field(
        ..., description="模板卡片类型"
    )

    # 通用字段
    source: TemplateCardSource | None = Field(None, description="卡片来源样式信息,不需要来源样式可不填写")
    action_menu: ActionMenu | None = Field(None, description="卡片右上角更多操作按钮")
    main_title: MainTitle | None = Field(None, description="主标题")
    quote_area: QuoteArea | None = Field(None, description="引用文献样式")

    # 文本通知型 & 图文展示型 & 按钮交互型通用字段
    sub_title_text: str | None = Field(None, description="二级普通文本,建议不超过160个字")
    horizontal_content_list: list[HorizontalContentItem] | None = Field(
        None, description="二级标题+文本列表,该字段可为空数组,但有数据的话需确认对应字段是否必填,列表长度不超过6"
    )

    # 文本通知型专用字段
    emphasis_content: EmphasisContent | None = Field(None, description="关键数据样式")
    jump_list: list[JumpListItem] | None = Field(
        None, description="跳转指引样式的列表,该字段可为空数组,但有数据的话需确认对应字段是否必填,列表长度不超过3"
    )

    # 图文展示型专用字段
    image_text_area: ImageTextArea | None = Field(
        None, description="左图右文样式,news_notice类型的卡片,card_image和image_text_area两者必填一个字段,不可都不填"
    )
    card_image: CardImage | None = Field(
        None, description="图片样式,news_notice类型的卡片,card_image和image_text_area两者必填一个字段,不可都不填"
    )
    vertical_content_list: list[VerticalContentItem] | None = Field(
        None, description="卡片二级垂直内容,该字段可为空数组,但有数据的话需确认对应字段是否必填,列表长度不超过4"
    )

    # 按钮交互型专用字段
    button_selection: ButtonSelection | None = Field(None, description="按钮型卡片的下拉框样式")
    button_list: list[ButtonItem] | None = Field(None, description="按钮列表,列表长度不超过6")

    # 投票选择型专用字段
    checkbox: Checkbox | None = Field(None, description="选择题样式")
    submit_button: SubmitButton | None = Field(None, description="提交按钮样式")

    # 多项选择型专用字段
    select_list: list[SelectList] | None = Field(
        None, description="下拉式的选择器列表,multiple_interaction类型的卡片该字段不可为空,一个消息最多支持 3 个选择器"
    )

    # 卡片动作和任务ID
    card_action: CardAction | None = Field(None, description="整体卡片的点击跳转事件")
    task_id: str | None = Field(None, description='任务id,同一个应用任务id不能重复,只能由数字、字母和"_-@"组成,最长128字节')


# ===== 发送应用消息请求和响应模型 =====


class SendAppMessageRequest(WeComApiModelBase):
    """发送应用消息请求"""

    # 接收者信息 (三者不能同时为空)
    touser: Annotated[
        str | None,
        Field(
            description='指定接收消息的成员,成员ID列表(多个接收者用"|"分隔,最多支持1000个)特殊情况:指定为"@all",则向该企业应用的全部成员发送',
        ),
    ]
    toparty: Annotated[
        str | None, Field(description='指定接收消息的部门,部门ID列表,多个接收者用"|"分隔,最多支持100个当touser为"@all"时忽略本参数')
    ] = None
    totag: Annotated[
        str | None, Field(description='指定接收消息的标签,标签ID列表,多个接收者用"|"分隔,最多支持100个当touser为"@all"时忽略本参数')
    ] = None

    # 消息类型和应用ID
    msgtype: Annotated[
        Literal["text", "image", "voice", "video", "file", "textcard", "news", "mpnews", "markdown", "miniprogram_notice", "template_card"],
        Field(description="消息类型"),
    ] = "text"
    agentid: Annotated[
        int,
        Field(
            description="应用的 agentid(整型). 自建应用可在应用设置页查看;第三方服务商场景可通过授权信息相关接口获取",
        ),
    ]

    # 各种消息类型的内容
    text: Annotated[TextContent | None, Field(description="文本消息内容")] = None
    image: Annotated[ImageContent | None, Field(description="图片消息内容")] = None
    voice: Annotated[VoiceContent | None, Field(description="语音消息内容")] = None
    video: Annotated[VideoContent | None, Field(description="视频消息内容")] = None
    file: Annotated[FileContent | None, Field(description="文件消息内容")] = None
    textcard: Annotated[TextCardContent | None, Field(description="文本卡片消息内容")] = None
    news: Annotated[NewsContent | None, Field(description="图文消息内容")] = None
    mpnews: Annotated[MpNewsContent | None, Field(description="图文消息(mpnews)内容")] = None
    markdown: Annotated[MarkdownContent | None, Field(description="markdown消息内容")] = None
    miniprogram_notice: Annotated[MiniProgramNoticeContent | None, Field(description="小程序通知消息内容")] = None
    template_card: Annotated[TemplateCardContent | None, Field(description="模板卡片消息内容")] = None

    # 可选参数
    safe: Annotated[
        Literal[0, 1, 2] | None,
        Field(
            description="表示是否是保密消息,0表示可对外分享,1表示不能分享且内容显示水印,2表示仅限在企业内分享,默认为0;注意仅mpnews类型的消息支持safe值为2,其他消息类型不支持"
        ),
    ] = None
    enable_id_trans: Annotated[Literal[0, 1] | None, Field(description="表示是否开启id转译,0表示否,1表示是,默认0")] = None
    enable_duplicate_check: Annotated[Literal[0, 1] | None, Field(description="表示是否开启重复消息检查,0表示否,1表示是,默认0")] = None
    duplicate_check_interval: Annotated[int | None, Field(description="表示是否重复消息检查的时间间隔,默认1800s,最大不超过4小时")] = None


class SendAppMessageResponse(WeComBaseResp):
    """发送应用消息响应"""

    invaliduser: str | None = Field(None, description="不合法的userid,不区分大小写,统一转为小写")
    invalidparty: str | None = Field(None, description="不合法的partyid")
    invalidtag: str | None = Field(None, description="不合法的标签id")
    unlicenseduser: str | None = Field(None, description="没有基础接口许可(包含已过期)的userid")
    msgid: str | None = Field(None, description="消息id,用于撤回应用消息")
    response_code: str | None = Field(
        None,
        description='仅消息类型为"按钮交互型","投票选择型"和"多项选择型"的模板卡片消息返回,应用可使用response_code调用更新模版卡片消息接口,72小时内有效,且只能使用一次',
    )

    def get_failure_reason_when_send_only_one_user(self) -> str:
        if self.invaliduser:
            return f"不合法的userid(已统一lowercase): {self.invaliduser}"
        if self.unlicenseduser:
            return f"没有基础接口许可(包含已过期)的userid: {self.unlicenseduser}"
        return ""
