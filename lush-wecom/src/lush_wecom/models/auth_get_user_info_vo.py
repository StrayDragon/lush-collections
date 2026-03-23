"""
获取访问用户身份相关模型
参考文档: https://developer.work.weixin.qq.com/document/path/91023
"""

from typing import Annotated

from pydantic import Field

from .common_vo import WeComBaseResp


class GetUserInfoResponse(WeComBaseResp):
    """获取访问用户身份响应

    返回结果说明:
    a) 当用户为企业成员时(无论是否在应用可见范围之内):
       - userid: 成员UserID
       - user_ticket: 成员票据(scope为snsapi_privateinfo且用户在应用可见范围内时返回)

    b) 非企业成员时:
       - openid: 非企业成员的标识
       - external_userid: 外部联系人id(用户是企业客户且跟进人在应用可见范围内时返回)
    """

    userid: Annotated[
        str | None,
        Field(
            description="成员UserID.若需要获得用户详情信息,可调用通讯录接口.如果是互联企业/企业互联/上下游,则返回的UserId格式如:CorpId/userid",
        ),
    ] = None
    user_ticket: Annotated[
        str | None,
        Field(
            description="成员票据,最大为512字节,有效期为1800s.scope为snsapi_privateinfo,且用户在应用可见范围之内时返回此参数",
        ),
    ] = None
    openid: Annotated[
        str | None,
        Field(
            description="非企业成员的标识,对当前企业唯一.不超过64字节",
        ),
    ] = None
    external_userid: Annotated[
        str | None,
        Field(
            description="外部联系人id,当且仅当用户是企业的客户,且跟进人在应用的可见范围内时返回",
        ),
    ] = None
