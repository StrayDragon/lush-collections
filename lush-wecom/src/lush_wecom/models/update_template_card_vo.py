"""
更新模板卡片消息相关模型
参考文档: https://developer.work.weixin.qq.com/document/path/94888
"""

from typing import Literal

from pydantic import Field

from .common_vo import WeComApiModelBase, WeComBaseResp
from .send_app_message_vo import TemplateCardContent

# ===== 更新按钮为不可点击状态模型 =====


class ButtonReplacement(WeComApiModelBase):
    """按钮替换信息"""

    replace_name: str = Field(..., description="需要更新的按钮的文案")


# ===== 更新模板卡片消息请求模型 =====


class UpdateTemplateCardRequest(WeComApiModelBase):
    """更新模板卡片消息请求"""

    # 接收者信息 (四者不能同时为空)
    userids: list[str] | None = Field(None, description="企业的成员ID列表(最多支持1000个)")
    partyids: list[int] | None = Field(None, description="企业的部门ID列表(最多支持100个)")
    tagids: list[int] | None = Field(None, description="企业的标签ID列表(最多支持100个)")
    atall: Literal[0, 1] | None = Field(None, description="更新整个任务接收人员,0表示否,1表示是")

    # 必填参数
    agentid: int = Field(..., description="应用的agentid")
    response_code: str = Field(
        ..., description="更新卡片所需要消费的code,可通过发消息接口和回调接口返回值获取,一个code只能调用一次该接口,且只能在72小时内调用"
    )

    # 可选参数
    enable_id_trans: Literal[0, 1] | None = Field(None, description="表示是否开启id转译,0表示否,1表示是,默认0")

    # 更新选项 (二选一)
    button: ButtonReplacement | None = Field(None, description="更新按钮为不可点击状态的信息")
    template_card: TemplateCardContent | None = Field(None, description="更新为新的卡片内容")


# ===== 更新模板卡片消息响应模型 =====


class UpdateTemplateCardResponse(WeComBaseResp):
    """更新模板卡片消息响应"""

    invaliduser: list[str] | None = Field(None, description="不合法的userid列表,不区分大小写,统一转为小写")
    invalidparty: list[int] | None = Field(None, description="不合法的partyid列表")
    invalidtag: list[int] | None = Field(None, description="不合法的标签id列表")
