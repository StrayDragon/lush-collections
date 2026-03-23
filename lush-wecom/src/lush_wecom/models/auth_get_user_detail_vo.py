"""
获取访问用户敏感信息相关模型
参考文档: https://developer.work.weixin.qq.com/document/path/95833
"""

from typing import Annotated

from pydantic import Field

from .common_vo import WeComBaseResp


class GetUserDetailResponse(WeComBaseResp):
    """获取访问用户敏感信息响应

    敏感字段说明:
    - 对于自建应用与代开发应用,敏感字段需要管理员在应用详情里选择
    - 成员oauth2授权时确认后才返回
    - 敏感字段包括: 性别、头像、员工个人二维码、手机、邮箱、企业邮箱、地址

    参考文档: https://developer.work.weixin.qq.com/document/path/95833
    """

    userid: Annotated[
        str | None,
        Field(description="成员UserID"),
    ] = None
    name: Annotated[
        str | None,
        Field(description="成员姓名"),
    ] = None
    gender: Annotated[
        str | None,
        Field(description="性别.0表示未定义,1表示男性,2表示女性.仅在用户同意snsapi_privateinfo授权时返回真实值,否则返回0"),
    ] = None
    avatar: Annotated[
        str | None,
        Field(description="头像url.仅在用户同意snsapi_privateinfo授权时返回真实头像,否则返回默认头像"),
    ] = None
    qr_code: Annotated[
        str | None,
        Field(description="员工个人二维码(扫描可添加为外部联系人),仅在用户同意snsapi_privateinfo授权时返回"),
    ] = None
    mobile: Annotated[
        str | None,
        Field(description="手机,仅在用户同意snsapi_privateinfo授权时返回,第三方应用不可获取"),
    ] = None
    email: Annotated[
        str | None,
        Field(description="邮箱,仅在用户同意snsapi_privateinfo授权时返回,第三方应用不可获取"),
    ] = None
    biz_mail: Annotated[
        str | None,
        Field(description="企业邮箱,仅在用户同意snsapi_privateinfo授权时返回,第三方应用不可获取"),
    ] = None
    address: Annotated[
        str | None,
        Field(description="地址,仅在用户同意snsapi_privateinfo授权时返回,第三方应用不可获取"),
    ] = None
