import httpx
from pydantic import ValidationError

from lush_wecom.core.exceptions import WeComAPIError
from lush_wecom.core.storage import AsyncBaseStorage, AsyncMemoryStorage, BaseStorage, MemoryStorage
from lush_wecom.models import common_vo


class WeComTokenClient:
    """基础企业微信客户端,负责获取access_token"""

    BASE_URL: str = "https://qyapi.weixin.qq.com/cgi-bin"

    def __init__(self, corpid: str, corpsecret: str, timeout: int = 10, mock_enabled: bool = False) -> None:
        # mock 模式允许 corpid/corpsecret 为空
        if not mock_enabled and (not corpid or not corpsecret):
            raise ValueError("corpid 和 corpsecret 不能为空")
        self.corpid: str = corpid
        self.corpsecret: str = corpsecret
        self.timeout: int = timeout
        self.session: httpx.Client = httpx.Client()
        self.mock_enabled: bool = mock_enabled

    def get_access_token(self) -> common_vo.GetAccessTokenResp:
        if self.mock_enabled:
            return common_vo.GetAccessTokenResp(errcode=0, errmsg="ok", access_token="wecom-mock-token", expires_in=7200)  # noqa: S106
        get_token_url = f"{self.BASE_URL}/gettoken"
        params = {"corpid": self.corpid, "corpsecret": self.corpsecret}
        try:
            response = self.session.get(get_token_url, params=params, timeout=self.timeout)
            _ = response.raise_for_status()
            token_resp = common_vo.GetAccessTokenResp.model_validate(response.json())
            if token_resp.errcode == 0:
                return token_resp
            raise WeComAPIError(
                f"获取 access_token 失败: {token_resp.errmsg}",
                errcode=token_resp.errcode,
            )
        except httpx.RequestError as e:
            raise WeComAPIError(f"网络请求失败: {e}") from e
        except (ValidationError, KeyError, ValueError) as e:
            raise WeComAPIError(f"解析API响应失败: {e}") from e


class WeComTokenManager:
    """
    企业微信access_token管理器,支持多种存储后端
    自动处理token失效和重试逻辑
    """

    def __init__(
        self,
        corpid: str,
        corpsecret: str,
        storage: BaseStorage | None = None,
        cache_key: str = "wecom_token:{corpid}",
        mock_enabled: bool = False,
    ) -> None:
        self.mock_enabled: bool = mock_enabled
        self.token_client: WeComTokenClient = WeComTokenClient(
            corpid=corpid,
            corpsecret=corpsecret,
            mock_enabled=mock_enabled,
        )
        self.storage: BaseStorage = storage or MemoryStorage()
        self.cache_key: str = cache_key.format(corpid=corpid)

    def get_token(self, force_refresh: bool = False) -> str:
        """
        获取access_token,优先从存储后端获取

        Args:
            force_refresh: 是否强制刷新token

        Returns:
            access_token字符串
        """
        if not force_refresh:
            # 直接从存储获取token字符串
            cached_token = self.storage.get(self.cache_key)
            if cached_token:
                return cached_token

        # Token无效或需要刷新,从服务器获取新Token(真实或mock 由 TokenClient 决定)
        resp = self.token_client.get_access_token()
        if resp.access_token and resp.expires_in:
            # 直接存储token字符串,过期时间由存储后端的TTL管理
            self.storage.set(self.cache_key, resp.access_token, resp.expires_in)
            return resp.access_token
        raise WeComAPIError("刷新 Token 失败,未获取到有效的 access_token")


class AsyncWeComTokenClient:
    BASE_URL: str = "https://qyapi.weixin.qq.com/cgi-bin"

    def __init__(self, corpid: str, corpsecret: str, timeout: int = 10, mock_enabled: bool = False) -> None:
        if not mock_enabled and (not corpid or not corpsecret):
            raise ValueError("corpid 和 corpsecret 不能为空")
        self.corpid = corpid
        self.corpsecret = corpsecret
        self.timeout = timeout
        self.session: httpx.AsyncClient = httpx.AsyncClient()
        self.mock_enabled: bool = mock_enabled

    async def get_access_token(self) -> common_vo.GetAccessTokenResp:
        if self.mock_enabled:
            return common_vo.GetAccessTokenResp(errcode=0, errmsg="ok", access_token="wecom-mock-token", expires_in=7200)  # noqa: S106
        get_token_url = f"{self.BASE_URL}/gettoken"
        params = {"corpid": self.corpid, "corpsecret": self.corpsecret}
        try:
            resp = await self.session.get(get_token_url, params=params, timeout=self.timeout)
            _ = resp.raise_for_status()
            token_resp = common_vo.GetAccessTokenResp.model_validate(resp.json())
            if token_resp.errcode == 0:
                return token_resp
            raise WeComAPIError(
                f"获取 access_token 失败: {token_resp.errmsg}",
                errcode=token_resp.errcode,
            )
        except httpx.RequestError as e:  # 网络层
            raise WeComAPIError(f"网络请求失败: {e}") from e
        except (ValidationError, KeyError, ValueError) as e:  # 解析层
            raise WeComAPIError(f"解析API响应失败: {e}") from e


class AsyncWeComTokenManager:
    """
    异步企业微信access_token管理器,支持异步存储后端
    自动处理token失效和重试逻辑
    """

    def __init__(
        self,
        corpid: str,
        corpsecret: str,
        storage: AsyncBaseStorage | None = None,
        cache_key: str = "wecom_token:{corpid}",
        mock_enabled: bool = False,  # 仅用于开发/测试流程; mock 返回的数据不完整,可能导致部分接口报错
    ) -> None:
        self.mock_enabled: bool = mock_enabled
        self.token_client: AsyncWeComTokenClient = AsyncWeComTokenClient(
            corpid=corpid,
            corpsecret=corpsecret,
            mock_enabled=mock_enabled,
        )
        self.storage: AsyncBaseStorage = storage or AsyncMemoryStorage()
        self.cache_key: str = cache_key.format(corpid=corpid)

    async def get_token(self, force_refresh: bool = False) -> str:
        """
        异步获取access_token,优先从存储后端获取

        Args:
            force_refresh: 是否强制刷新token

        Returns:
            access_token字符串
        """
        if not force_refresh:
            # 异步从存储获取token字符串
            cached_token = await self.storage.get(self.cache_key)
            if cached_token:
                return cached_token

        # Token无效或需要刷新,从服务器获取新Token
        resp = await self.token_client.get_access_token()
        if resp.access_token and resp.expires_in:
            # 异步存储token字符串,过期时间由存储后端的TTL管理
            await self.storage.set(self.cache_key, resp.access_token, resp.expires_in)
            return resp.access_token
        raise WeComAPIError("刷新 Token 失败,未获取到有效的 access_token")
