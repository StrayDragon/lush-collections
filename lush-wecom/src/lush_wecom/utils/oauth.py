from typing import Literal
from urllib.parse import quote


def build_oauth_authorize_url(
    corpid: str,
    redirect_uri: str,
    scope: Literal["snsapi_base", "snsapi_privateinfo"] = "snsapi_base",
    state: str = "",
    agentid: int | str | None = None,
) -> str:
    """构建企业微信OAuth2.0网页授权URL

    参考文档: https://developer.work.weixin.qq.com/document/path/91022

    Args:
        corpid: 企业ID
        redirect_uri: 授权后重定向的回调链接,需要urlencode
        scope: 应用授权作用域
            - snsapi_base: 静默授权,可获取成员的基础信息(UserId与DeviceId)
            - snsapi_privateinfo: 手动授权,可获取成员的敏感信息,但不包含手机、邮箱等敏感信息
        state: 重定向后会带上state参数,企业可以填写a-zA-Z0-9的参数值,长度不可超过128个字节
        agentid: 企业应用的id.当scope是snsapi_userinfo或snsapi_privateinfo时,该参数必填

    Returns:
        完整的授权URL

    Example:
        >>> url = build_oauth_authorize_url(
        ...     corpid="ww123123123", redirect_uri="https://example.com/callback", scope="snsapi_base", state="demo"
        ... )
        >>> print(url)
        https://open.weixin.qq.com/connect/oauth2/authorize?appid=ww123123123&redirect_uri=https%3A%2F%2Fexample.com%2Fcallback&response_type=code&scope=snsapi_base&state=demo#wechat_redirect

    Note:
        1. redirect_uri必须是已在企业微信管理后台配置的可信域名
        2. scope为snsapi_privateinfo时需要用户手动确认授权
        3. state参数会在授权回调时原样返回
        4. 生成的URL需要在企业微信客户端内打开才能完成授权
    """
    base_url = "https://open.weixin.qq.com/connect/oauth2/authorize"

    # 构建参数
    params = {
        "appid": corpid,
        "redirect_uri": quote(redirect_uri, safe=""),
        "response_type": "code",
        "scope": scope,
    }

    # state参数(可选)
    if state:
        params["state"] = state

    # agentid参数(scope为snsapi_privateinfo时必填)
    if agentid is not None:
        params["agentid"] = str(agentid)

    # 拼接查询参数
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])

    # 返回完整URL(注意结尾的#wechat_redirect)
    return f"{base_url}?{query_string}#wechat_redirect"
