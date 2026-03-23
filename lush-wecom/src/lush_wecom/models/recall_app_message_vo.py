"""
撤回应用消息相关模型
参考文档: https://developer.work.weixin.qq.com/document/path/94867
"""

from pydantic import Field

from .common_vo import WeComApiModelBase, WeComBaseResp


class RecallAppMessageRequest(WeComApiModelBase):
    """撤回应用消息请求"""

    msgid: str = Field(..., description="消息ID,从应用发送消息接口处获得")


class RecallAppMessageResponse(WeComBaseResp):
    """撤回应用消息响应"""

    # 只需要基础的errcode和errmsg字段
