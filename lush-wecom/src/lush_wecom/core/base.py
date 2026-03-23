"""
企业微信SDK整合版本

核心功能:
1. 统一的企业微信客户端,整合基础API、外部联系人API、媒体API
2. 自动的access_token管理和缓存(Redis后端)
3. 自动重试机制,当token失效时自动刷新并重试
4. 无感知的API调用体验

主要类:
- WeComClient: 统一的企业微信客户端
- WeComTokenManager: token管理器,支持Redis缓存
- RedisStorage: Redis存储后端
"""

import contextlib
import logging
import time
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any, TypeVar, cast

import httpx
from pydantic import ValidationError

from lush_wecom.core.const import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY,
    DEFAULT_TIMEOUT,
    RETRYABLE_ERROR_CODES,
    TOKEN_INVALID_ERROR_CODES,
)
from lush_wecom.core.exceptions import InvalidTokenError, WeComAPIError, WeComHTTPError, WeComResponseValidationError
from lush_wecom.core.token_mgr import AsyncWeComTokenManager, WeComTokenManager
from lush_wecom.models import common_vo
from lush_wecom.utils.retry import aretry_on_error, aretry_on_error_iter, retry_on_error

with contextlib.suppress(ImportError):
    pass

T = TypeVar("T", bound=common_vo.WeComBaseResp)

_PolyModelFactory: Any
try:
    from polyfactory.factories.pydantic_factory import ModelFactory as _PolyModelFactory
except Exception:  # pragma: no cover
    _PolyModelFactory = None


def _generate_mock_response(response_model: "type[T]") -> T:
    if _PolyModelFactory is None:
        raise RuntimeError("仅开发时可用!")

    class _Factory(_PolyModelFactory):  # type: ignore[misc, valid-type]
        __model__ = response_model

        @classmethod
        def errcode(cls) -> int:
            # return cls.__random__.choice([0])
            return 0

    return cast("T", _Factory.build())


# 获取logger
_LOGGER = logging.getLogger(__name__)


# Type aliases for commonly used models
WeComBaseResp = common_vo.WeComBaseResp
GetAccessTokenResp = common_vo.GetAccessTokenResp


def should_retry_wecom_error(error: Exception) -> bool:
    if isinstance(error, InvalidTokenError):
        return True
    if isinstance(error, WeComAPIError):
        return error.errcode in RETRYABLE_ERROR_CODES
    return False


# ===== 请求状态管理 =====


class RequestState:
    """请求状态管理类,用于跟踪重试过程中的状态"""

    def __init__(self) -> None:
        self.token_error_count: int = 0
        self.attempt_count: int = 0
        self.last_token_refresh_time: float = 0.0

    def reset(self) -> None:
        """重置状态"""
        self.token_error_count = 0
        self.attempt_count = 0
        self.last_token_refresh_time = 0.0

    def mark_token_error(self) -> None:
        """标记发生了token错误"""
        self.token_error_count += 1
        _LOGGER.debug(f"Token错误计数: {self.token_error_count}")

    def should_refresh_token(self) -> bool:
        """判断是否需要刷新token"""
        # 有token错误且距离上次刷新超过1秒(避免频繁刷新)
        current_time = time.time()
        return bool(self.token_error_count > 0 and current_time - self.last_token_refresh_time > 1.0)

    def mark_token_refreshed(self) -> None:
        """标记token已刷新"""
        self.last_token_refresh_time = time.time()
        self.token_error_count = 0  # 重置错误计数
        _LOGGER.debug("Token已刷新,错误计数重置")


# ===== 基础客户端类 =====


def handle_requests_http_error(resp: httpx.Response) -> None:
    """处理HTTP请求错误"""
    try:
        _ = resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise WeComHTTPError(f"HTTP 请求失败: {e}", e) from e


# ===== 统一客户端 =====


class WeComClientBase:
    """
    统一的企业微信客户端,整合所有API功能

    功能包括:
    1. 自动token管理和缓存
    2. 自动重试机制
    3. 外部联系人群发API
    4. 媒体上传API
    5. 其他企业微信API
    6. 日志记录和回调钩子支持
    """

    BASE_URL: str = "https://qyapi.weixin.qq.com/cgi-bin"

    def __init__(
        self,
        token_manager: WeComTokenManager,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
        on_request: Callable[[str, str, dict[str, Any]], None] | None = None,
        on_retry: Callable[[Exception, int], None] | None = None,
        on_token_refresh: Callable[[], None] | None = None,
        mock_enabled: bool = False,
    ) -> None:
        """
        初始化企业微信客户端

        Args:
            token_manager: Token管理器
            timeout: 请求超时时间
            max_retries: 最大重试次数
            retry_delay: 重试间隔时间(秒)
            on_request: 请求回调钩子,参数: (method, url, kwargs)
            on_retry: 重试回调钩子,参数: (exception, attempt)
            on_token_refresh: Token刷新回调钩子
        """
        self.token_manager: WeComTokenManager = token_manager
        self.timeout: int = timeout
        self.session: httpx.Client = httpx.Client()
        self.max_retries: int = max_retries
        self.retry_delay: float = retry_delay

        # 回调钩子
        self.on_request: Callable[[str, str, dict[str, Any]], None] | None = on_request
        self.on_retry: Callable[[Exception, int], None] | None = on_retry
        self.on_token_refresh: Callable[[], None] | None = on_token_refresh

        # Mock 返回数据, 不走真实请求
        self.mock_enabled: bool = mock_enabled

    def _get_access_token_with_state(self, request_state: RequestState) -> str:
        """
        根据请求状态获取access_token

        Args:
            request_state: 请求状态对象

        Returns:
            access_token字符串
        """
        access_token = ""
        if request_state.should_refresh_token():
            _LOGGER.info("检测到token错误,开始刷新token")
            access_token = self.token_manager.get_token(force_refresh=True)
            request_state.mark_token_refreshed()
            # 调用token刷新回调
            if self.on_token_refresh:
                self.on_token_refresh()

        if not access_token:
            # 获取access_token
            access_token = self.token_manager.get_token()

        return access_token

    def _make_request(
        self,
        method: str,
        endpoint: str,
        response_model: type[T],
        **kwargs: Any,
    ) -> T:
        """
        内部请求方法,统一处理API请求

        Args:
            method: HTTP方法
            endpoint: API端点
            response_model: 响应模型类
            forward_params: 其他请求参数

        Returns:
            响应模型实例
        """
        if self.mock_enabled:
            return _generate_mock_response(response_model)

        request_state = RequestState()

        def _do_single_request() -> T:
            """执行单次请求"""
            # 获取access_token
            access_token = self._get_access_token_with_state(request_state)
            url = f"{self.BASE_URL}{endpoint}"
            if "params" not in kwargs:
                kwargs["params"] = {}
            kwargs["params"]["access_token"] = access_token

            # 设置超时
            kwargs["timeout"] = kwargs.get("timeout", self.timeout)

            # 调用请求回调
            if self.on_request:
                self.on_request(method, url, kwargs)

            _LOGGER.debug(f"发起请求: {method} {url}")

            try:
                response = self.session.request(method, url, **kwargs)
                handle_requests_http_error(response)

                data = cast("dict[str, Any]", response.json())

                # 检查API级别的错误码
                errcode = data.get("errcode", 0)
                if errcode != 0:
                    errmsg = data.get("errmsg", "未知错误")
                    if errcode in TOKEN_INVALID_ERROR_CODES:
                        # 标记token错误
                        request_state.mark_token_error()
                        raise InvalidTokenError(errcode=errcode, errmsg=errmsg)
                    raise WeComAPIError(errcode=errcode, errmsg=errmsg)

                # 使用Pydantic模型验证和解析
                return response_model.model_validate(data)

            except ValidationError as e:
                raise WeComResponseValidationError("API响应数据验证失败") from e
            except (ValueError, TypeError) as e:
                # httpx.Response.json() 在JSON解析失败时抛出ValueError
                raise WeComAPIError("无法解析API响应,可能不是有效的JSON") from e
            except httpx.RequestError as e:
                raise WeComAPIError(f"网络请求失败: {e}") from e

        # 使用重试装饰器
        @retry_on_error(
            max_retries=self.max_retries,
            exceptions=(WeComAPIError, InvalidTokenError, httpx.RequestError),
            should_retry=should_retry_wecom_error,
            on_retry_callback=self.on_retry,
        )
        def _do_request_with_retry() -> T:
            return _do_single_request()

        return _do_request_with_retry()

    def _make_stream_request(
        self,
        method: str,
        endpoint: str,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        range_header: str | None = None,
        **kwargs: Any,
    ) -> Iterator[bytes]:
        """
        通用流式请求方法,用于下载文件等场景

        Args:
            method: HTTP方法
            endpoint: API端点
            chunk_size: 分块大小,默认20MB
            range_header: Range请求头,用于断点下载,格式如 "bytes=0-1023"
            **kwargs: 其他请求参数

        Returns:
            文件流迭代器

        Raises:
            WeComAPIError: 企业微信API错误
            InvalidTokenError: Token无效错误
        """
        if self.mock_enabled:

            def _mock_stream() -> Iterator[bytes]:
                chunk = b"WECOM-MOCK-DATA" * 1024
                for _ in range(3):
                    yield chunk[:chunk_size]

            return _mock_stream()

        request_state = RequestState()

        def _do_single_stream_request() -> Iterator[bytes]:
            """执行单次流式请求"""
            # 获取access_token
            access_token = self._get_access_token_with_state(request_state)
            url = f"{self.BASE_URL}{endpoint}"
            if "params" not in kwargs:
                kwargs["params"] = {}
            kwargs["params"]["access_token"] = access_token

            # 设置流式下载
            kwargs["stream"] = True
            kwargs["timeout"] = kwargs.get("timeout", self.timeout)

            # 添加Range头支持断点下载
            if range_header:
                if "headers" not in kwargs:
                    kwargs["headers"] = {}
                kwargs["headers"]["Range"] = range_header

            # 调用请求回调
            if self.on_request:
                self.on_request(method, url, kwargs)

            _LOGGER.debug(f"发起流式请求: {method} {url}")

            with self.session.stream(method, url, **kwargs) as response:
                # 检查是否返回了JSON错误响应
                content_type = str(response.headers.get("Content-Type", ""))
                if "application/json" in content_type:
                    data = response.json()
                    errcode = data.get("errcode", -1)
                    if errcode in TOKEN_INVALID_ERROR_CODES:
                        # 标记token错误
                        request_state.mark_token_error()
                        raise InvalidTokenError(
                            errcode=errcode,
                            errmsg=data.get("errmsg", "未知错误"),
                        )
                    raise WeComAPIError(
                        errcode=errcode,
                        errmsg=data.get("errmsg", "未知错误"),
                    )

                handle_requests_http_error(response)
                yield from response.iter_bytes(chunk_size=chunk_size)

        # 使用重试装饰器,与_make_request保持一致的风格
        @retry_on_error(
            max_retries=self.max_retries,
            exceptions=(WeComAPIError, InvalidTokenError, httpx.RequestError),
            should_retry=should_retry_wecom_error,
            on_retry_callback=self.on_retry,
        )
        def _do_stream_request_with_retry() -> Iterator[bytes]:
            return _do_single_stream_request()

        return _do_stream_request_with_retry()


class AsyncWeComClientBase:
    BASE_URL: str = "https://qyapi.weixin.qq.com/cgi-bin"

    def __init__(
        self,
        token_manager: AsyncWeComTokenManager,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
        on_request: Callable[[str, str, dict[str, Any]], None] | None = None,
        on_retry: Callable[[Exception, int], None] | None = None,
        on_token_refresh: Callable[[], None] | None = None,
        # 仅用于开发/测试流程; mock 返回的数据不完整,可能导致部分接口报错
        mock_enabled: bool | None = None,
    ) -> None:
        self.token_manager = token_manager
        self.timeout = timeout
        self.session: httpx.AsyncClient = httpx.AsyncClient()
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.on_request = on_request
        self.on_retry = on_retry
        self.on_token_refresh = on_token_refresh

        self.mock_enabled: bool = bool(mock_enabled) if mock_enabled is not None else False

    async def _get_access_token_with_state(self, request_state: RequestState) -> str:
        access_token = ""
        if request_state.should_refresh_token():
            _LOGGER.info("检测到token错误,开始刷新token")
            access_token = await self.token_manager.get_token(force_refresh=True)
            request_state.mark_token_refreshed()
            if self.on_token_refresh:
                self.on_token_refresh()
        if not access_token:
            access_token = await self.token_manager.get_token()
        return access_token

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        response_model: type[T],
        **kwargs: Any,
    ) -> T:
        if self.mock_enabled:
            return _generate_mock_response(response_model)

        request_state = RequestState()

        async def _do_single_request() -> T:
            access_token = await self._get_access_token_with_state(request_state)
            url = f"{self.BASE_URL}{endpoint}"
            if "params" not in kwargs:
                kwargs["params"] = {}
            kwargs["params"]["access_token"] = access_token
            kwargs["timeout"] = kwargs.get("timeout", self.timeout)

            if self.on_request:
                self.on_request(method, url, kwargs)

            _LOGGER.debug("发起请求: %s %s", method, url)

            try:
                resp = await self.session.request(method, url, **kwargs)
                try:
                    _ = resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    raise WeComHTTPError("HTTP 请求失败", e) from e

                data = cast("dict[str, Any]", resp.json())
                errcode = data.get("errcode", 0)
                if errcode != 0:
                    errmsg = data.get("errmsg", "未知错误")
                    if errcode in TOKEN_INVALID_ERROR_CODES:
                        request_state.mark_token_error()
                        raise InvalidTokenError(errcode=errcode, errmsg=errmsg)
                    raise WeComAPIError(errcode=errcode, errmsg=errmsg)

                return response_model.model_validate(data)
            except ValidationError as e:
                raise WeComResponseValidationError("API响应数据验证失败") from e
            except (ValueError, TypeError) as e:
                raise WeComAPIError("无法解析问题,可能请求/返回结构不是有效的JSON") from e
            except httpx.RequestError as e:
                raise WeComAPIError(f"网络请求失败: {e}") from e

        return await aretry_on_error(
            max_retries=self.max_retries,
            should_retry=should_retry_wecom_error,
            on_retry_callback=self.on_retry,
        )(_do_single_request)()

    def _make_stream_request(
        self,
        method: str,
        endpoint: str,
        *,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        range_header: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[bytes]:
        if self.mock_enabled:

            async def _mock_astream() -> AsyncIterator[bytes]:
                chunk = b"WECOM-MOCK-DATA" * 1024
                for _ in range(3):
                    yield chunk[:chunk_size]

            return _mock_astream()

        request_state = RequestState()

        async def _do_single_stream_request() -> AsyncIterator[bytes]:
            access_token = await self._get_access_token_with_state(request_state)
            url = f"{self.BASE_URL}{endpoint}"
            if "params" not in kwargs:
                kwargs["params"] = {}
            kwargs["params"]["access_token"] = access_token
            kwargs["timeout"] = kwargs.get("timeout", self.timeout)

            if range_header:
                if "headers" not in kwargs:
                    kwargs["headers"] = {}
                kwargs["headers"]["Range"] = range_header

            if self.on_request:
                self.on_request(method, url, kwargs)

            _LOGGER.debug("发起流式请求: %s %s", method, url)

            async with self.session.stream(method, url, **kwargs) as resp:
                content_type = str(resp.headers.get("Content-Type", ""))
                if "application/json" in content_type:
                    _ = await resp.aread()
                    data = resp.json()
                    errcode = data.get("errcode", -1)
                    if errcode in TOKEN_INVALID_ERROR_CODES:
                        request_state.mark_token_error()
                        raise InvalidTokenError(
                            errcode=errcode,
                            errmsg=data.get("errmsg", "未知错误"),
                        )
                    raise WeComAPIError(
                        errcode=errcode,
                        errmsg=data.get("errmsg", "未知错误"),
                    )

                try:
                    _ = resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    raise WeComHTTPError("HTTP 请求失败", e) from e

                async for chunk in resp.aiter_bytes(chunk_size=chunk_size):
                    yield chunk

        # 直接对异步生成器应用重试装饰器, 每次重试重新创建并消费生成器
        @aretry_on_error_iter(
            max_retries=self.max_retries,
            should_retry=should_retry_wecom_error,
            on_retry_callback=self.on_retry,
        )
        async def _gen() -> AsyncIterator[bytes]:
            async for chunk in _do_single_stream_request():
                yield chunk

        return _gen()
